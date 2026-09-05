from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from supabase import Client

from models.mock_exam import (
    GeneratedMockExam,
    MockExamAttemptResult,
    MockExamSaveResult,
    MockExamState,
    MockExamSummary,
)


def _normalize_uuid(value: str, field_name: str) -> str:
    """외부 식별자를 표준 UUID 문자열로 검증합니다."""

    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def save_mock_exam(
    *,
    supabase: Client,
    user_id: str,
    plan_id: str,
    generation_key: str,
    generated: GeneratedMockExam,
    reference_learning_material_id: str | None = None,
    reference_review_material_id: str | None = None,
) -> MockExamSaveResult:
    """검증된 모의 평가를 멱등 서버 RPC로 저장합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_plan_id = _normalize_uuid(plan_id, "학습계획 ID")
    normalized_generation_key = _normalize_uuid(generation_key, "생성 식별자")
    if (
        reference_learning_material_id is not None
        and reference_review_material_id is not None
    ):
        raise ValueError("모의 평가 참고자료는 하나만 선택할 수 있습니다.")
    if not isinstance(generated, GeneratedMockExam):
        raise ValueError("저장할 모의 평가 생성 결과가 올바르지 않습니다.")
    normalized_learning_material_id = (
        _normalize_uuid(reference_learning_material_id, "원본 참고자료 ID")
        if reference_learning_material_id is not None
        else None
    )
    normalized_review_material_id = (
        _normalize_uuid(reference_review_material_id, "AI 참고자료 ID")
        if reference_review_material_id is not None
        else None
    )

    exam = generated.exam
    response = (
        supabase.rpc(
            "save_mock_exam",
            {
                "p_plan_id": normalized_plan_id,
                "p_generation_key": normalized_generation_key,
                "p_title": exam.title,
                "p_recommended_minutes": exam.recommended_minutes,
                "p_questions": [
                    question.model_dump(mode="json")
                    for question in exam.questions
                ],
                "p_prompt_version": generated.prompt_version,
                "p_model_name": generated.model_name,
                "p_reference_learning_material_id": (
                    normalized_learning_material_id
                ),
                "p_reference_review_material_id": (
                    normalized_review_material_id
                ),
            },
        )
        .execute()
    )
    try:
        result = MockExamSaveResult.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("모의 평가 저장 결과 형식이 올바르지 않습니다.") from error
    if str(result.user_id) != normalized_user_id:
        raise RuntimeError("저장된 모의 평가의 사용자 소유권이 올바르지 않습니다.")
    if str(result.plan_id) != normalized_plan_id:
        raise RuntimeError("저장된 모의 평가의 학습계획 연결이 올바르지 않습니다.")
    if str(result.generation_key) != normalized_generation_key:
        raise RuntimeError("모의 평가 생성 식별자가 요청과 다릅니다.")
    return result


def get_mock_exams_by_plan(
    *,
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> list[MockExamSummary]:
    """본인 계획의 모의 평가 목록과 성적 요약을 조회합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_plan_id = _normalize_uuid(plan_id, "학습계획 ID")
    response = (
        supabase.rpc(
            "get_mock_exams_by_plan",
            {"p_plan_id": normalized_plan_id},
        )
        .execute()
    )
    try:
        summaries = TypeAdapter(list[MockExamSummary]).validate_python(
            response.data or []
        )
    except ValidationError as error:
        raise RuntimeError("모의 평가 목록 형식이 올바르지 않습니다.") from error
    for summary in summaries:
        if (
            str(summary.user_id) != normalized_user_id
            or str(summary.plan_id) != normalized_plan_id
        ):
            raise RuntimeError("모의 평가 목록의 사용자 소유권이 올바르지 않습니다.")
    return summaries


def get_mock_exam_state(
    *,
    supabase: Client,
    user_id: str,
    exam_id: str,
) -> MockExamState:
    """정답을 제거한 모의 평가와 본인의 최신 결과를 조회합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_exam_id = _normalize_uuid(exam_id, "모의 평가 ID")
    response = (
        supabase.rpc(
            "get_mock_exam_state",
            {"p_mock_exam_id": normalized_exam_id},
        )
        .execute()
    )
    try:
        state = MockExamState.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("모의 평가 조회 결과 형식이 올바르지 않습니다.") from error
    if str(state.user_id) != normalized_user_id:
        raise RuntimeError("모의 평가 조회 결과의 사용자 소유권이 올바르지 않습니다.")
    if str(state.exam_id) != normalized_exam_id:
        raise RuntimeError("모의 평가 조회 결과가 요청한 평가와 다릅니다.")
    return state


def submit_mock_exam_attempt(
    *,
    supabase: Client,
    user_id: str,
    exam_id: str,
    answers: list[int],
    submission_key: str,
) -> MockExamAttemptResult:
    """모의 평가 답안을 서버에서 채점하고 멱등 저장합니다."""

    _normalize_uuid(user_id, "사용자 ID")
    normalized_exam_id = _normalize_uuid(exam_id, "모의 평가 ID")
    normalized_submission_key = _normalize_uuid(submission_key, "제출 식별자")
    if not isinstance(answers, list) or len(answers) != 15:
        raise ValueError("모의 평가 답안은 정확히 15개여야 합니다.")
    if any(
        isinstance(answer, bool)
        or not isinstance(answer, int)
        or answer not in range(4)
        for answer in answers
    ):
        raise ValueError("각 모의 평가 답안은 0부터 3 사이의 정수여야 합니다.")

    response = (
        supabase.rpc(
            "submit_mock_exam_attempt",
            {
                "p_mock_exam_id": normalized_exam_id,
                "p_answers": answers,
                "p_submission_key": normalized_submission_key,
            },
        )
        .execute()
    )
    try:
        result = MockExamAttemptResult.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError("모의 평가 제출 결과 형식이 올바르지 않습니다.") from error
    if str(result.mock_exam_id) != normalized_exam_id:
        raise RuntimeError("모의 평가 제출 결과의 평가 연결이 올바르지 않습니다.")
    if str(result.submission_key) != normalized_submission_key:
        raise RuntimeError("모의 평가 제출 식별자가 요청과 다릅니다.")
    return result
