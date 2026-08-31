from collections.abc import MutableMapping
from typing import Any


LEARNING_CONTEXT_PREFIX = "learning_context_"
PLAN_ID_KEY = "learning_context_plan_id"
TASK_ID_KEY = "learning_context_task_id"
SOURCE_KEY = "learning_context_source"
PENDING_NAVIGATION_KEY = "learning_context_pending_navigation"
TUTOR_PAGE_TITLE = "단계별 힌트 AI 튜터"


def request_tutor_learning_context(
    state: MutableMapping[str, Any],
    *,
    plan_id: str,
    task_id: str,
    source: str,
) -> None:
    """선택한 계획·과제로 튜터를 이어갈 세션 문맥을 기록합니다."""

    normalized_plan_id = str(plan_id).strip()
    normalized_task_id = str(task_id).strip()
    if not normalized_plan_id or not normalized_task_id:
        raise ValueError("튜터로 전달할 계획과 과제 ID가 필요합니다.")

    state[PLAN_ID_KEY] = normalized_plan_id
    state[TASK_ID_KEY] = normalized_task_id
    state[SOURCE_KEY] = str(source).strip()
    state[PENDING_NAVIGATION_KEY] = TUTOR_PAGE_TITLE


def get_learning_context(
    state: MutableMapping[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """현재 전달 대기 중인 계획·과제·출처를 반환합니다."""

    plan_id = state.get(PLAN_ID_KEY)
    task_id = state.get(TASK_ID_KEY)
    source = state.get(SOURCE_KEY)
    return (
        str(plan_id) if plan_id else None,
        str(task_id) if task_id else None,
        str(source) if source else None,
    )


def has_learning_context(state: MutableMapping[str, Any]) -> bool:
    """유효성 검사 전의 학습 문맥 요청이 남아 있는지 확인합니다."""

    plan_id, task_id, _source = get_learning_context(state)
    return plan_id is not None and task_id is not None


def clear_learning_context(state: MutableMapping[str, Any]) -> None:
    """학습 문맥 접두사 상태만 제거해 다른 화면 상태를 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(LEARNING_CONTEXT_PREFIX):
            state.pop(key, None)
