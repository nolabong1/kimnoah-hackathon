from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.learning_assessment import (
    GeneratedLearningAssessmentPair,
    LearningAssessmentAttemptResult,
    LearningAssessmentPairSaveResult,
    LearningAssessmentPlanState,
)


def _normalize_uuid(value: str, field_name: str) -> str:
    """외부에서 받은 식별자를 표준 UUID 문자열로 검증합니다."""

    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def save_learning_assessment_pair(
    *,
    supabase: Client,
    user_id: str,
    plan_id: str,
    pair_key: str,
    generated: GeneratedLearningAssessmentPair,
) -> LearningAssessmentPairSaveResult:
    """검증된 사전·사후 평가를 서버 트랜잭션으로 함께 저장합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_plan_id = _normalize_uuid(plan_id, "학습계획 ID")
    normalized_pair_key = _normalize_uuid(pair_key, "평가 쌍 식별자")
    pair = generated.pair
    response = (
        supabase.rpc(
            "save_learning_assessment_pair",
            {
                "p_plan_id": normalized_plan_id,
                "p_pair_key": normalized_pair_key,
                "p_pre_title": pair.pre_assessment.title,
                "p_pre_questions": [
                    question.model_dump(mode="json")
                    for question in pair.pre_assessment.questions
                ],
                "p_post_title": pair.post_assessment.title,
                "p_post_questions": [
                    question.model_dump(mode="json")
                    for question in pair.post_assessment.questions
                ],
                "p_prompt_version": generated.prompt_version,
                "p_model_name": generated.model_name,
            },
        )
        .execute()
    )
    try:
        result = LearningAssessmentPairSaveResult.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("평가 저장 결과 형식이 올바르지 않습니다.") from error
    if str(result.user_id) != normalized_user_id:
        raise RuntimeError("저장된 평가의 사용자 소유권이 올바르지 않습니다.")
    if str(result.plan_id) != normalized_plan_id:
        raise RuntimeError("저장된 평가의 학습계획 연결이 올바르지 않습니다.")
    if str(result.pair_key) != normalized_pair_key:
        raise RuntimeError("저장된 평가 쌍 식별자가 요청과 다릅니다.")
    return result


def get_learning_assessment_state(
    *,
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> LearningAssessmentPlanState:
    """본인 계획의 평가와 서버 판정 응시 자격을 조회합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_plan_id = _normalize_uuid(plan_id, "학습계획 ID")
    response = (
        supabase.rpc(
            "get_learning_assessment_state",
            {"p_plan_id": normalized_plan_id},
        )
        .execute()
    )
    try:
        state = LearningAssessmentPlanState.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("평가 조회 결과 형식이 올바르지 않습니다.") from error
    if str(state.user_id) != normalized_user_id:
        raise RuntimeError("평가 조회 결과의 사용자 소유권이 올바르지 않습니다.")
    if str(state.plan_id) != normalized_plan_id:
        raise RuntimeError("평가 조회 결과의 학습계획 연결이 올바르지 않습니다.")
    return state


def submit_learning_assessment_attempt(
    *,
    supabase: Client,
    user_id: str,
    assessment_id: str,
    answers: list[int],
    submission_key: str,
) -> LearningAssessmentAttemptResult:
    """공식 평가 답안을 서버에서 한 번만 채점하고 저장합니다."""

    _normalize_uuid(user_id, "사용자 ID")
    normalized_assessment_id = _normalize_uuid(assessment_id, "평가 ID")
    normalized_submission_key = _normalize_uuid(submission_key, "제출 식별자")
    if not isinstance(answers, list) or not 6 <= len(answers) <= 15:
        raise ValueError("평가 답안은 6개 이상 15개 이하여야 합니다.")
    if any(
        isinstance(answer, bool)
        or not isinstance(answer, int)
        or answer not in range(4)
        for answer in answers
    ):
        raise ValueError("각 평가 답안은 0부터 3 사이의 정수여야 합니다.")

    response = (
        supabase.rpc(
            "submit_learning_assessment_attempt",
            {
                "p_assessment_id": normalized_assessment_id,
                "p_answers": answers,
                "p_submission_key": normalized_submission_key,
            },
        )
        .execute()
    )
    try:
        result = LearningAssessmentAttemptResult.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("평가 제출 결과 형식이 올바르지 않습니다.") from error
    if str(result.assessment_id) != normalized_assessment_id:
        raise RuntimeError("평가 제출 결과의 평가 연결이 요청과 다릅니다.")
    if str(result.submission_key) != normalized_submission_key:
        raise RuntimeError("평가 제출 결과의 제출 식별자가 요청과 다릅니다.")
    return result
