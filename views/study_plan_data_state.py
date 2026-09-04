from collections.abc import Callable, MutableMapping
from copy import deepcopy
from time import monotonic
from typing import Any

from models.learning_objective import StoredLearningObjective
from services.learning_objective_repository import (
    get_learning_objectives_by_plan_ids,
)
from services.study_plan_repository import (
    get_study_plan_tasks,
    get_study_tasks_by_plan_ids,
    get_user_study_plans,
)
from views.cache_config import DEFAULT_SESSION_CACHE_TTL_SECONDS


STUDY_PLAN_DATA_STATE_PREFIX = "study_plan_data_"
PLAN_LIST_SNAPSHOT_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}plans"
PLAN_LIST_USER_ID_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}user_id"
PLAN_LIST_LOADED_AT_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}loaded_at"
TASK_SNAPSHOTS_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}tasks_by_plan"
TASK_LOADED_AT_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}tasks_loaded_at"
TASK_USER_ID_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}tasks_user_id"
OBJECTIVE_SNAPSHOTS_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}objectives_by_plan"
OBJECTIVE_LOADED_AT_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}objectives_loaded_at"
OBJECTIVE_USER_ID_KEY = f"{STUDY_PLAN_DATA_STATE_PREFIX}objectives_user_id"


def _is_plan_list(value: object) -> bool:
    """저장 계획 목록 캐시에 필요한 최소 응답 형태를 확인합니다."""

    return isinstance(value, list) and all(
        isinstance(plan, dict)
        and isinstance(plan.get("id"), str)
        and bool(plan["id"].strip())
        for plan in value
    )


def _is_task_list(value: object) -> bool:
    """계획별 과제 캐시에 필요한 최소 응답 형태를 확인합니다."""

    return isinstance(value, list) and all(
        isinstance(task, dict) for task in value
    )


def _is_objective_list(value: object) -> bool:
    """목표 선택 UI에 필요한 최소 응답 형태를 확인합니다."""

    return isinstance(value, list) and all(
        bool(str(getattr(objective, "id", "")).strip())
        and bool(str(getattr(objective, "title", "")).strip())
        for objective in value
    )


def get_study_plan_list_snapshot(
    client,
    user_id: str,
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    """현재 사용자의 저장 계획 목록을 짧은 세션 캐시로 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")

    current_time = monotonic() if now is None else float(now)
    snapshot = state.get(PLAN_LIST_SNAPSHOT_KEY)
    loaded_at = state.get(PLAN_LIST_LOADED_AT_KEY)
    cache_age = (
        current_time - loaded_at
        if isinstance(loaded_at, (int, float))
        and not isinstance(loaded_at, bool)
        else DEFAULT_SESSION_CACHE_TTL_SECONDS
    )
    cache_is_current = (
        state.get(PLAN_LIST_USER_ID_KEY) == normalized_user_id
        and _is_plan_list(snapshot)
        and 0 <= cache_age < DEFAULT_SESSION_CACHE_TTL_SECONDS
    )
    if cache_is_current:
        return deepcopy(snapshot)

    loaded_plans = (
        loader()
        if loader is not None
        else get_user_study_plans(client, normalized_user_id)
    )
    if not _is_plan_list(loaded_plans):
        raise RuntimeError("학습계획 목록 조회 결과가 올바르지 않습니다.")

    stored_snapshot = deepcopy(loaded_plans)
    state[PLAN_LIST_SNAPSHOT_KEY] = stored_snapshot
    state[PLAN_LIST_USER_ID_KEY] = normalized_user_id
    state[PLAN_LIST_LOADED_AT_KEY] = current_time
    return deepcopy(stored_snapshot)


def invalidate_study_plan_list_snapshot(
    state: MutableMapping[str, Any],
) -> None:
    """계획 생성·삭제 뒤 다음 조회가 서버 값을 사용하도록 무효화합니다."""

    for key in (
        PLAN_LIST_SNAPSHOT_KEY,
        PLAN_LIST_USER_ID_KEY,
        PLAN_LIST_LOADED_AT_KEY,
    ):
        state.pop(key, None)


def get_learning_objectives_by_plan_ids_snapshot(
    client,
    user_id: str,
    plan_ids: list[str],
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[
        [list[str]],
        dict[str, list[StoredLearningObjective]],
    ]
    | None = None,
) -> dict[str, list[StoredLearningObjective]]:
    """여러 계획의 학습목표를 계획별 짧은 세션 캐시로 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")

    normalized_plan_ids = list(
        dict.fromkeys(
            plan_id.strip()
            for plan_id in plan_ids
            if isinstance(plan_id, str) and plan_id.strip()
        )
    )
    if not normalized_plan_ids:
        return {}

    current_time = monotonic() if now is None else float(now)
    cached_objectives = state.get(OBJECTIVE_SNAPSHOTS_KEY)
    cached_loaded_at = state.get(OBJECTIVE_LOADED_AT_KEY)
    if (
        state.get(OBJECTIVE_USER_ID_KEY) != normalized_user_id
        or not isinstance(cached_objectives, dict)
        or not isinstance(cached_loaded_at, dict)
    ):
        cached_objectives = {}
        cached_loaded_at = {}
    else:
        cached_objectives = deepcopy(cached_objectives)
        cached_loaded_at = dict(cached_loaded_at)

    missing_plan_ids: list[str] = []
    for plan_id in normalized_plan_ids:
        loaded_at = cached_loaded_at.get(plan_id)
        cache_age = (
            current_time - loaded_at
            if isinstance(loaded_at, (int, float))
            and not isinstance(loaded_at, bool)
            else DEFAULT_SESSION_CACHE_TTL_SECONDS
        )
        if not (
            _is_objective_list(cached_objectives.get(plan_id))
            and 0 <= cache_age < DEFAULT_SESSION_CACHE_TTL_SECONDS
        ):
            missing_plan_ids.append(plan_id)

    if missing_plan_ids:
        loaded_by_plan = (
            loader(missing_plan_ids)
            if loader is not None
            else get_learning_objectives_by_plan_ids(
                client,
                normalized_user_id,
                missing_plan_ids,
            )
        )
        if not isinstance(loaded_by_plan, dict):
            raise RuntimeError("학습목표 목록 조회 결과가 올바르지 않습니다.")
        for plan_id in missing_plan_ids:
            loaded_objectives = loaded_by_plan.get(plan_id)
            if not _is_objective_list(loaded_objectives):
                raise RuntimeError("학습목표 목록 조회 결과가 올바르지 않습니다.")
            cached_objectives[plan_id] = deepcopy(loaded_objectives)
            cached_loaded_at[plan_id] = current_time

    state[OBJECTIVE_SNAPSHOTS_KEY] = cached_objectives
    state[OBJECTIVE_LOADED_AT_KEY] = cached_loaded_at
    state[OBJECTIVE_USER_ID_KEY] = normalized_user_id
    return {
        plan_id: deepcopy(cached_objectives[plan_id])
        for plan_id in normalized_plan_ids
    }


def invalidate_learning_objective_snapshots(
    state: MutableMapping[str, Any],
    plan_id: str | None = None,
) -> None:
    """계획 생성·삭제 뒤 전체 또는 선택 계획의 목표 캐시를 무효화합니다."""

    if plan_id is None:
        for key in (
            OBJECTIVE_SNAPSHOTS_KEY,
            OBJECTIVE_LOADED_AT_KEY,
            OBJECTIVE_USER_ID_KEY,
        ):
            state.pop(key, None)
        return

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        return
    for key in (OBJECTIVE_SNAPSHOTS_KEY, OBJECTIVE_LOADED_AT_KEY):
        value = state.get(key)
        if isinstance(value, dict):
            updated = dict(value)
            updated.pop(normalized_plan_id, None)
            state[key] = updated


def get_study_tasks_by_plan_ids_snapshot(
    client,
    user_id: str,
    plan_ids: list[str],
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[[list[str]], dict[str, list[dict]]] | None = None,
) -> dict[str, list[dict]]:
    """여러 계획의 과제를 계획별 짧은 세션 캐시로 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")

    normalized_plan_ids = list(
        dict.fromkeys(
            plan_id.strip()
            for plan_id in plan_ids
            if isinstance(plan_id, str) and plan_id.strip()
        )
    )
    if not normalized_plan_ids:
        return {}

    current_time = monotonic() if now is None else float(now)
    cached_tasks = state.get(TASK_SNAPSHOTS_KEY)
    cached_loaded_at = state.get(TASK_LOADED_AT_KEY)
    if (
        state.get(TASK_USER_ID_KEY) != normalized_user_id
        or not isinstance(cached_tasks, dict)
        or not isinstance(cached_loaded_at, dict)
    ):
        cached_tasks = {}
        cached_loaded_at = {}
    else:
        cached_tasks = deepcopy(cached_tasks)
        cached_loaded_at = dict(cached_loaded_at)

    missing_plan_ids: list[str] = []
    for plan_id in normalized_plan_ids:
        loaded_at = cached_loaded_at.get(plan_id)
        cache_age = (
            current_time - loaded_at
            if isinstance(loaded_at, (int, float))
            and not isinstance(loaded_at, bool)
            else DEFAULT_SESSION_CACHE_TTL_SECONDS
        )
        if not (
            _is_task_list(cached_tasks.get(plan_id))
            and 0 <= cache_age < DEFAULT_SESSION_CACHE_TTL_SECONDS
        ):
            missing_plan_ids.append(plan_id)

    if missing_plan_ids:
        loaded_by_plan = (
            loader(missing_plan_ids)
            if loader is not None
            else get_study_tasks_by_plan_ids(
                client,
                normalized_user_id,
                missing_plan_ids,
            )
        )
        if not isinstance(loaded_by_plan, dict):
            raise RuntimeError("학습과제 목록 조회 결과가 올바르지 않습니다.")
        for plan_id in missing_plan_ids:
            loaded_tasks = loaded_by_plan.get(plan_id)
            if not _is_task_list(loaded_tasks):
                raise RuntimeError("학습과제 목록 조회 결과가 올바르지 않습니다.")
            cached_tasks[plan_id] = deepcopy(loaded_tasks)
            cached_loaded_at[plan_id] = current_time

    state[TASK_SNAPSHOTS_KEY] = cached_tasks
    state[TASK_LOADED_AT_KEY] = cached_loaded_at
    state[TASK_USER_ID_KEY] = normalized_user_id
    return {
        plan_id: deepcopy(cached_tasks[plan_id])
        for plan_id in normalized_plan_ids
    }


def get_study_plan_tasks_snapshot(
    client,
    user_id: str,
    plan_id: str,
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    """선택 계획 하나의 과제를 공통 계획별 캐시에서 반환합니다."""

    normalized_plan_id = plan_id.strip() if isinstance(plan_id, str) else ""
    if not normalized_plan_id:
        raise ValueError("학습계획 ID가 필요합니다.")

    tasks_by_plan = get_study_tasks_by_plan_ids_snapshot(
        client,
        user_id,
        [normalized_plan_id],
        state,
        now=now,
        loader=(
            (lambda _: {normalized_plan_id: loader()})
            if loader is not None
            else (
                lambda _: {
                    normalized_plan_id: get_study_plan_tasks(
                        client,
                        str(user_id).strip(),
                        normalized_plan_id,
                    )
                }
            )
        ),
    )
    return tasks_by_plan[normalized_plan_id]


def invalidate_study_task_snapshots(
    state: MutableMapping[str, Any],
    plan_id: str | None = None,
) -> None:
    """과제 변경 뒤 전체 또는 선택 계획의 과제 캐시를 무효화합니다."""

    if plan_id is None:
        for key in (
            TASK_SNAPSHOTS_KEY,
            TASK_LOADED_AT_KEY,
            TASK_USER_ID_KEY,
        ):
            state.pop(key, None)
        return

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        return
    for key in (TASK_SNAPSHOTS_KEY, TASK_LOADED_AT_KEY):
        value = state.get(key)
        if isinstance(value, dict):
            updated = dict(value)
            updated.pop(normalized_plan_id, None)
            state[key] = updated


def clear_study_plan_data_state(state: MutableMapping[str, Any]) -> None:
    """로그아웃할 때 현재 사용자의 계획 조회 캐시만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(STUDY_PLAN_DATA_STATE_PREFIX):
            state.pop(key, None)
