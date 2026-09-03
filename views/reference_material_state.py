from collections.abc import Callable, MutableMapping
from copy import deepcopy
from time import monotonic
from typing import Any

from services.review_material_repository import (
    get_learning_materials_by_plan,
    get_review_materials_by_plan,
    get_source_review_material_bundles_by_plan,
)


REFERENCE_MATERIAL_STATE_PREFIX = "reference_material_data_"
MATERIAL_SNAPSHOTS_KEY = f"{REFERENCE_MATERIAL_STATE_PREFIX}by_plan"
MATERIAL_LOADED_AT_KEY = f"{REFERENCE_MATERIAL_STATE_PREFIX}loaded_at"
MATERIAL_USER_ID_KEY = f"{REFERENCE_MATERIAL_STATE_PREFIX}user_id"
MATERIAL_CACHE_TTL_SECONDS = 30.0
SOURCE_BUNDLE_SNAPSHOTS_KEY = (
    f"{REFERENCE_MATERIAL_STATE_PREFIX}source_bundles_by_plan"
)
SOURCE_BUNDLE_LOADED_AT_KEY = (
    f"{REFERENCE_MATERIAL_STATE_PREFIX}source_bundles_loaded_at"
)


def _is_material_list(value: object) -> bool:
    """참고자료 캐시에 필요한 최소 응답 형태를 확인합니다."""

    return isinstance(value, list) and all(
        isinstance(material, dict) for material in value
    )


def _clear_if_user_changed(
    state: MutableMapping[str, Any],
    user_id: str,
) -> None:
    """한 브라우저 세션에서 사용자가 바뀌면 모든 자료 캐시를 제거합니다."""

    cached_user_id = state.get(MATERIAL_USER_ID_KEY)
    if cached_user_id is not None and cached_user_id != user_id:
        clear_reference_material_state(state)


def get_reference_materials_snapshot(
    client,
    user_id: str,
    plan_id: str,
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[[], tuple[list[dict], list[dict]]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """선택 계획의 원본·AI 자료를 짧은 사용자별 세션 캐시로 반환합니다."""

    normalized_user_id = str(user_id).strip()
    normalized_plan_id = plan_id.strip() if isinstance(plan_id, str) else ""
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")
    if not normalized_plan_id:
        raise ValueError("학습계획 ID가 필요합니다.")

    _clear_if_user_changed(state, normalized_user_id)
    current_time = monotonic() if now is None else float(now)
    snapshots = state.get(MATERIAL_SNAPSHOTS_KEY)
    loaded_at_by_plan = state.get(MATERIAL_LOADED_AT_KEY)
    if (
        state.get(MATERIAL_USER_ID_KEY) != normalized_user_id
        or not isinstance(snapshots, dict)
        or not isinstance(loaded_at_by_plan, dict)
    ):
        snapshots = {}
        loaded_at_by_plan = {}
    else:
        snapshots = deepcopy(snapshots)
        loaded_at_by_plan = dict(loaded_at_by_plan)

    snapshot = snapshots.get(normalized_plan_id)
    loaded_at = loaded_at_by_plan.get(normalized_plan_id)
    cache_age = (
        current_time - loaded_at
        if isinstance(loaded_at, (int, float))
        and not isinstance(loaded_at, bool)
        else MATERIAL_CACHE_TTL_SECONDS
    )
    cache_is_current = (
        isinstance(snapshot, dict)
        and _is_material_list(snapshot.get("learning"))
        and _is_material_list(snapshot.get("review"))
        and 0 <= cache_age < MATERIAL_CACHE_TTL_SECONDS
    )
    if not cache_is_current:
        learning_materials, review_materials = (
            loader()
            if loader is not None
            else (
                get_learning_materials_by_plan(
                    client,
                    normalized_user_id,
                    normalized_plan_id,
                ),
                get_review_materials_by_plan(
                    client,
                    normalized_user_id,
                    normalized_plan_id,
                ),
            )
        )
        if not (
            _is_material_list(learning_materials)
            and _is_material_list(review_materials)
        ):
            raise RuntimeError("참고자료 목록 조회 결과가 올바르지 않습니다.")
        snapshot = {
            "learning": deepcopy(learning_materials),
            "review": deepcopy(review_materials),
        }
        snapshots[normalized_plan_id] = snapshot
        loaded_at_by_plan[normalized_plan_id] = current_time

    state[MATERIAL_SNAPSHOTS_KEY] = snapshots
    state[MATERIAL_LOADED_AT_KEY] = loaded_at_by_plan
    state[MATERIAL_USER_ID_KEY] = normalized_user_id
    return deepcopy(snapshot["learning"]), deepcopy(snapshot["review"])


def get_source_review_bundles_snapshot(
    client,
    user_id: str,
    plan_id: str,
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
    loader: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    """원본 기반 복습자료 보관함을 짧은 사용자별 세션 캐시로 반환합니다."""

    normalized_user_id = str(user_id).strip()
    normalized_plan_id = plan_id.strip() if isinstance(plan_id, str) else ""
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")
    if not normalized_plan_id:
        raise ValueError("학습계획 ID가 필요합니다.")

    _clear_if_user_changed(state, normalized_user_id)
    current_time = monotonic() if now is None else float(now)
    snapshots = state.get(SOURCE_BUNDLE_SNAPSHOTS_KEY)
    loaded_at_by_plan = state.get(SOURCE_BUNDLE_LOADED_AT_KEY)
    if not isinstance(snapshots, dict) or not isinstance(
        loaded_at_by_plan,
        dict,
    ):
        snapshots = {}
        loaded_at_by_plan = {}
    else:
        snapshots = deepcopy(snapshots)
        loaded_at_by_plan = dict(loaded_at_by_plan)

    snapshot = snapshots.get(normalized_plan_id)
    loaded_at = loaded_at_by_plan.get(normalized_plan_id)
    cache_age = (
        current_time - loaded_at
        if isinstance(loaded_at, (int, float))
        and not isinstance(loaded_at, bool)
        else MATERIAL_CACHE_TTL_SECONDS
    )
    if not (
        _is_material_list(snapshot)
        and 0 <= cache_age < MATERIAL_CACHE_TTL_SECONDS
    ):
        snapshot = (
            loader()
            if loader is not None
            else get_source_review_material_bundles_by_plan(
                client,
                normalized_user_id,
                normalized_plan_id,
            )
        )
        if not _is_material_list(snapshot):
            raise RuntimeError("저장된 복습자료 조회 결과가 올바르지 않습니다.")
        snapshots[normalized_plan_id] = deepcopy(snapshot)
        loaded_at_by_plan[normalized_plan_id] = current_time

    state[SOURCE_BUNDLE_SNAPSHOTS_KEY] = snapshots
    state[SOURCE_BUNDLE_LOADED_AT_KEY] = loaded_at_by_plan
    state[MATERIAL_USER_ID_KEY] = normalized_user_id
    return deepcopy(snapshot)


def invalidate_reference_material_snapshots(
    state: MutableMapping[str, Any],
    plan_id: str | None = None,
) -> None:
    """자료 변경 뒤 전체 또는 선택 계획의 참고자료 캐시를 무효화합니다."""

    if plan_id is None:
        for key in (
            MATERIAL_SNAPSHOTS_KEY,
            MATERIAL_LOADED_AT_KEY,
            MATERIAL_USER_ID_KEY,
            SOURCE_BUNDLE_SNAPSHOTS_KEY,
            SOURCE_BUNDLE_LOADED_AT_KEY,
        ):
            state.pop(key, None)
        return

    normalized_plan_id = str(plan_id).strip()
    if not normalized_plan_id:
        return
    for key in (
        MATERIAL_SNAPSHOTS_KEY,
        MATERIAL_LOADED_AT_KEY,
        SOURCE_BUNDLE_SNAPSHOTS_KEY,
        SOURCE_BUNDLE_LOADED_AT_KEY,
    ):
        value = state.get(key)
        if isinstance(value, dict):
            updated = dict(value)
            updated.pop(normalized_plan_id, None)
            state[key] = updated


def clear_reference_material_state(state: MutableMapping[str, Any]) -> None:
    """로그아웃할 때 현재 사용자의 참고자료 캐시만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(REFERENCE_MATERIAL_STATE_PREFIX):
            state.pop(key, None)
