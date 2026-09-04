import hashlib
from collections.abc import MutableMapping
from typing import Any

from models.tutor import TutorGuidance, TutorHint


TUTOR_STATE_PREFIX = "tutor_"
ACTIVE_SESSION_ID_KEY = "tutor_active_session_id"
ACTIVE_USER_ID_KEY = "tutor_active_user_id"
ACTIVE_PLAN_ID_KEY = "tutor_active_plan_id"
ACTIVE_TASK_ID_KEY = "tutor_active_task_id"
ACTIVE_MATERIAL_KEY = "tutor_active_material_key"
COURSE_NAME_KEY = "tutor_course_name"
TASK_TITLE_KEY = "tutor_task_title"
REFERENCE_TITLE_KEY = "tutor_reference_title"
REFERENCE_CONTEXT_KEY = "tutor_reference_context"
REFERENCE_LIMITED_KEY = "tutor_reference_was_limited"
PROBLEM_IMAGES_KEY = "tutor_problem_images"
QUESTION_KEY = "tutor_question"
ORIGINAL_ATTEMPT_KEY = "tutor_original_attempt"
GUIDANCE_KEY = "tutor_guidance"
VISIBLE_HINT_LEVEL_KEY = "tutor_visible_hint_level"
FINAL_CONFIRMATION_PENDING_KEY = "tutor_final_confirmation_pending"
FINAL_ANSWER_CONFIRMED_KEY = "tutor_final_answer_confirmed"
LATEST_FEEDBACK_KEY = "tutor_latest_feedback"
FEEDBACK_FINGERPRINT_KEY = "tutor_feedback_fingerprint"
REQUEST_IN_PROGRESS_KEY = "tutor_request_in_progress"
FEEDBACK_IN_PROGRESS_KEY = "tutor_feedback_in_progress"


def create_tutor_session_state(
    *,
    session_id: str,
    user_id: str,
    plan_id: str,
    task_id: str | None,
    material_key: str | None,
    course_name: str,
    task_title: str | None,
    reference_title: str | None,
    reference_context: str | None,
    reference_was_limited: bool,
    question: str,
    original_attempt: str,
    guidance: TutorGuidance,
    problem_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """새 튜터 세션의 초기 상태를 생성합니다."""

    return {
        ACTIVE_SESSION_ID_KEY: session_id,
        ACTIVE_USER_ID_KEY: user_id,
        ACTIVE_PLAN_ID_KEY: plan_id,
        ACTIVE_TASK_ID_KEY: task_id,
        ACTIVE_MATERIAL_KEY: material_key,
        COURSE_NAME_KEY: course_name,
        TASK_TITLE_KEY: task_title,
        REFERENCE_TITLE_KEY: reference_title,
        REFERENCE_CONTEXT_KEY: reference_context,
        REFERENCE_LIMITED_KEY: reference_was_limited,
        PROBLEM_IMAGES_KEY: problem_images or [],
        QUESTION_KEY: question,
        ORIGINAL_ATTEMPT_KEY: original_attempt,
        GUIDANCE_KEY: guidance.model_dump(),
        VISIBLE_HINT_LEVEL_KEY: 1,
        FINAL_CONFIRMATION_PENDING_KEY: False,
        FINAL_ANSWER_CONFIRMED_KEY: False,
        LATEST_FEEDBACK_KEY: None,
        FEEDBACK_FINGERPRINT_KEY: None,
        REQUEST_IN_PROGRESS_KEY: False,
        FEEDBACK_IN_PROGRESS_KEY: False,
    }


def clear_tutor_state(state: MutableMapping[str, Any]) -> None:
    """`tutor_` 접두사 상태만 제거해 다른 화면 상태를 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(TUTOR_STATE_PREFIX):
            state.pop(key, None)


def get_visible_hints(
    guidance: TutorGuidance,
    visible_hint_level: int,
) -> list[TutorHint]:
    """현재 단계까지 공개할 힌트만 반환합니다."""

    normalized_level = min(3, max(1, visible_hint_level))
    return [
        hint
        for hint in guidance.hints
        if hint.level <= normalized_level
    ]


def advance_hint_level(current_level: int) -> int:
    """API 호출 없이 다음 힌트 단계로 이동합니다."""

    return min(3, max(1, current_level) + 1)


def previous_hint_level(current_level: int) -> int:
    """API 호출 없이 이전 힌트 단계로 이동합니다."""

    return max(1, min(3, current_level) - 1)


def is_final_solution_visible(state: MutableMapping[str, Any]) -> bool:
    """명시적인 정답 확인 상태인지 판정합니다."""

    return bool(state.get(FINAL_ANSWER_CONFIRMED_KEY, False))


def build_feedback_fingerprint(
    session_id: str,
    visible_hint_level: int,
    revised_attempt: str,
) -> str:
    """같은 풀이 점검 요청의 연속 제출을 식별합니다."""

    source = "\x1f".join(
        [session_id, str(visible_hint_level), revised_attempt.strip()]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
