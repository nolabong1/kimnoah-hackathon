from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

from models.mock_exam import GeneratedMockExam


MOCK_EXAM_PREFIX = "mock_exam_"
GENERATED_PLAN_ID_KEY = "mock_exam_generated_plan_id"
GENERATED_REFERENCE_KEY = "mock_exam_generated_reference_key"
GENERATED_EXAM_KEY = "mock_exam_generated_exam"
GENERATION_REQUEST_KEY = "mock_exam_generation_request_key"
SELECTED_EXAM_ID_KEY = "mock_exam_selected_exam_id"
MESSAGE_KEY = "mock_exam_message"


def store_generated_mock_exam(
    state: MutableMapping[str, Any],
    *,
    plan_id: str,
    reference_key: str | None,
    generated: GeneratedMockExam,
) -> str:
    """저장 재시도에 사용할 AI 결과와 생성 식별자를 보존합니다."""

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        raise ValueError("모의 평가를 저장할 학습계획 ID가 필요합니다.")
    if not isinstance(generated, GeneratedMockExam):
        raise ValueError("저장할 모의 평가 생성 결과가 올바르지 않습니다.")
    generation_key = str(uuid4())
    state[GENERATED_PLAN_ID_KEY] = normalized_plan_id
    state[GENERATED_REFERENCE_KEY] = reference_key
    state[GENERATED_EXAM_KEY] = generated
    state[GENERATION_REQUEST_KEY] = generation_key
    return generation_key


def get_generated_mock_exam(
    state: MutableMapping[str, Any],
    *,
    plan_id: str,
    reference_key: str | None,
) -> tuple[GeneratedMockExam, str] | None:
    """동일 계획과 참고자료에서 저장 대기 중인 AI 결과만 반환합니다."""

    if state.get(GENERATED_PLAN_ID_KEY) != str(plan_id):
        return None
    if state.get(GENERATED_REFERENCE_KEY) != reference_key:
        return None
    generated = state.get(GENERATED_EXAM_KEY)
    generation_key = state.get(GENERATION_REQUEST_KEY)
    if not isinstance(generated, GeneratedMockExam):
        return None
    if not isinstance(generation_key, str) or not generation_key:
        return None
    return generated, generation_key


def clear_generated_mock_exam(state: MutableMapping[str, Any]) -> None:
    """저장 완료된 모의 평가 생성 임시 상태만 제거합니다."""

    for key in (
        GENERATED_PLAN_ID_KEY,
        GENERATED_REFERENCE_KEY,
        GENERATED_EXAM_KEY,
        GENERATION_REQUEST_KEY,
    ):
        state.pop(key, None)


def get_or_create_submission_request(
    state: MutableMapping[str, Any],
    *,
    exam_id: str,
    answers: list[int],
) -> str:
    """같은 모의 평가·답안 재시도에 같은 제출 키를 사용합니다."""

    normalized_exam_id = str(exam_id).strip()
    if not normalized_exam_id:
        raise ValueError("제출할 모의 평가 ID가 필요합니다.")
    state_key = f"{MOCK_EXAM_PREFIX}submission_{normalized_exam_id}"
    existing = state.get(state_key)
    if (
        isinstance(existing, dict)
        and existing.get("answers") == answers
        and isinstance(existing.get("submission_key"), str)
    ):
        return existing["submission_key"]
    submission_key = str(uuid4())
    state[state_key] = {
        "answers": list(answers),
        "submission_key": submission_key,
    }
    return submission_key


def clear_submission_request(
    state: MutableMapping[str, Any],
    exam_id: str,
) -> None:
    """서버 저장 성공 후 해당 모의 평가 제출 상태만 제거합니다."""

    state.pop(f"{MOCK_EXAM_PREFIX}submission_{exam_id}", None)


def clear_mock_exam_state(state: MutableMapping[str, Any]) -> None:
    """로그아웃 시 모의 평가 접두사 상태만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(MOCK_EXAM_PREFIX):
            state.pop(key, None)
