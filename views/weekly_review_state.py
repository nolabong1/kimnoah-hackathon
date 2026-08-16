from collections.abc import MutableMapping
from typing import Any

from models.study_plan import WeeklyStudyPlan


WEEKLY_REVIEW_STATE_PREFIX = "weekly_review_"
PLAN_SELECT_KEY = "weekly_review_selected_plan_id"
ACTIVE_PLAN_ID_KEY = "weekly_review_active_plan_id"
REQUEST_RUNNING_KEY = "weekly_review_request_running"
REGENERATION_CONFIRM_KEY = "weekly_review_regeneration_confirm"
NEXT_PLAN_RUNNING_KEY = "weekly_review_next_plan_running"
NEXT_PLAN_DRAFT_KEY = "weekly_review_next_plan_draft"
NEXT_PLAN_METADATA_KEY = "weekly_review_next_plan_metadata"
NEXT_PLAN_SAVED_KEY = "weekly_review_next_plan_saved"
NEXT_PLAN_SAVED_ID_KEY = "weekly_review_next_plan_saved_id"
SAVE_RUNNING_KEY = "weekly_review_save_running"
SUCCESS_MESSAGE_KEY = "weekly_review_success_message"
PENDING_NAVIGATION_KEY = "weekly_review_pending_navigation"


def clear_weekly_review_state(state: MutableMapping[str, Any]) -> None:
    """주간 회고 접두사 상태만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(WEEKLY_REVIEW_STATE_PREFIX):
            state.pop(key, None)


def apply_selected_plan_state(
    state: MutableMapping[str, Any],
    selected_plan_id: str,
) -> bool:
    """계획이 바뀌면 선택 위젯 외의 호환되지 않는 상태만 정리합니다."""

    previous_plan_id = state.get(ACTIVE_PLAN_ID_KEY)
    if previous_plan_id in {None, selected_plan_id}:
        state[ACTIVE_PLAN_ID_KEY] = selected_plan_id
        return False

    for key in list(state.keys()):
        if (
            str(key).startswith(WEEKLY_REVIEW_STATE_PREFIX)
            and key != PLAN_SELECT_KEY
        ):
            state.pop(key, None)
    state[ACTIVE_PLAN_ID_KEY] = selected_plan_id
    return True


def create_next_plan_draft_state(
    plan: WeeklyStudyPlan,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """저장되지 않은 다음 주 계획 미리보기 상태를 생성합니다."""

    return {
        NEXT_PLAN_DRAFT_KEY: plan.model_dump(mode="json"),
        NEXT_PLAN_METADATA_KEY: dict(metadata),
        NEXT_PLAN_SAVED_KEY: False,
        NEXT_PLAN_SAVED_ID_KEY: None,
    }


def clear_next_plan_draft(state: MutableMapping[str, Any]) -> None:
    """입력값은 유지하고 생성된 다음 계획 미리보기만 제거합니다."""

    for key in (
        NEXT_PLAN_DRAFT_KEY,
        NEXT_PLAN_METADATA_KEY,
        NEXT_PLAN_SAVED_KEY,
        NEXT_PLAN_SAVED_ID_KEY,
    ):
        state.pop(key, None)
