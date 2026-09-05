from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

from models.learning_assessment import GeneratedLearningAssessmentPair


LEARNING_ASSESSMENT_PREFIX = "learning_assessment_"
PENDING_NAVIGATION_KEY = "learning_assessment_pending_navigation"
PENDING_PLAN_ID_KEY = "learning_assessment_pending_plan_id"
PERFORMANCE_PAGE_TITLE = "학습 성과 리포트"
GENERATED_PLAN_ID_KEY = "learning_assessment_generated_plan_id"
GENERATED_PAIR_KEY = "learning_assessment_generated_pair"
PAIR_REQUEST_KEY = "learning_assessment_pair_request_key"
MESSAGE_KEY = "learning_assessment_message"


def request_learning_assessment_navigation(
    state: MutableMapping[str, Any],
    plan_id: str,
) -> None:
    """학습 성과 화면의 선택 계획을 평가 영역으로 연결합니다."""

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        raise ValueError("평가로 이동할 학습계획 ID가 필요합니다.")
    state[PENDING_PLAN_ID_KEY] = normalized_plan_id
    state[PENDING_NAVIGATION_KEY] = PERFORMANCE_PAGE_TITLE


def consume_pending_assessment_plan(
    state: MutableMapping[str, Any],
) -> str | None:
    """평가 화면으로 전달된 계획 ID를 한 번만 반환합니다."""

    plan_id = state.pop(PENDING_PLAN_ID_KEY, None)
    return str(plan_id) if plan_id else None


def store_generated_assessment_pair(
    state: MutableMapping[str, Any],
    *,
    plan_id: str,
    generated: GeneratedLearningAssessmentPair,
) -> str:
    """저장 재시도에 사용할 평가 쌍과 고정 요청 키를 보존합니다."""

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        raise ValueError("평가를 저장할 학습계획 ID가 필요합니다.")
    pair_key = str(uuid4())
    state[GENERATED_PLAN_ID_KEY] = normalized_plan_id
    state[GENERATED_PAIR_KEY] = generated
    state[PAIR_REQUEST_KEY] = pair_key
    return pair_key


def get_generated_assessment_pair(
    state: MutableMapping[str, Any],
    *,
    plan_id: str,
) -> tuple[GeneratedLearningAssessmentPair, str] | None:
    """같은 계획에서만 저장 대기 중인 평가 쌍을 반환합니다."""

    if state.get(GENERATED_PLAN_ID_KEY) != str(plan_id):
        return None
    generated = state.get(GENERATED_PAIR_KEY)
    pair_key = state.get(PAIR_REQUEST_KEY)
    if not isinstance(generated, GeneratedLearningAssessmentPair):
        return None
    if not isinstance(pair_key, str) or not pair_key:
        return None
    return generated, pair_key


def clear_generated_assessment_pair(
    state: MutableMapping[str, Any],
) -> None:
    """저장 완료된 평가 생성 임시 상태만 제거합니다."""

    for key in (
        GENERATED_PLAN_ID_KEY,
        GENERATED_PAIR_KEY,
        PAIR_REQUEST_KEY,
    ):
        state.pop(key, None)


def get_or_create_submission_request(
    state: MutableMapping[str, Any],
    *,
    assessment_id: str,
    answers: list[int],
) -> str:
    """같은 평가·답안 재시도에는 기존 제출 식별자를 재사용합니다."""

    normalized_assessment_id = str(assessment_id).strip()
    if not normalized_assessment_id:
        raise ValueError("제출할 평가 ID가 필요합니다.")
    request_state_key = (
        f"{LEARNING_ASSESSMENT_PREFIX}submission_{normalized_assessment_id}"
    )
    existing = state.get(request_state_key)
    if (
        isinstance(existing, dict)
        and existing.get("answers") == answers
        and isinstance(existing.get("submission_key"), str)
    ):
        return existing["submission_key"]

    submission_key = str(uuid4())
    state[request_state_key] = {
        "answers": list(answers),
        "submission_key": submission_key,
    }
    return submission_key


def clear_submission_request(
    state: MutableMapping[str, Any],
    assessment_id: str,
) -> None:
    """서버 제출 완료 후 해당 평가의 재시도 상태만 제거합니다."""

    state.pop(
        f"{LEARNING_ASSESSMENT_PREFIX}submission_{assessment_id}",
        None,
    )


def clear_learning_assessment_state(
    state: MutableMapping[str, Any],
) -> None:
    """로그아웃 시 평가 접두사 상태만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(LEARNING_ASSESSMENT_PREFIX):
            state.pop(key, None)
