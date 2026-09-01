from collections.abc import Callable, Mapping, MutableMapping
from time import monotonic
from typing import Any


SHOP_STATE_PREFIX = "shop_"
SUCCESS_MESSAGE_KEY = "shop_success_message"
PURCHASE_IN_PROGRESS_KEY = "shop_purchase_in_progress"
PURCHASE_REVEAL_KEY = "shop_purchase_reveal"
CATEGORY_FILTER_KEY = "shop_category_filter"
COLLECTION_CATEGORY_FILTER_KEY = "shop_collection_category_filter"
COLLECTION_STATUS_FILTER_KEY = "shop_collection_status_filter"
ROOM_SAVE_IN_PROGRESS_KEY = "shop_room_save_in_progress"
ROOM_SUCCESS_MESSAGE_KEY = "shop_room_success_message"
ROOM_SAVE_REVEAL_KEY = "shop_room_save_reveal"
ROOM_EDITOR_COMPONENT_KEY = "shop_room_direct_editor"
ROOM_TRANSFORMS_DRAFT_KEY = "shop_room_transforms_draft"
ROOM_EQUIPMENT_DRAFT_KEY = "shop_room_equipment_draft"
ROOM_SAVED_SOURCE_KEY = "shop_room_saved_source"
SHOP_DATA_SNAPSHOT_KEY = "shop_data_snapshot"
SHOP_DATA_USER_ID_KEY = "shop_data_snapshot_user_id"
SHOP_DATA_LOADED_AT_KEY = "shop_data_snapshot_loaded_at"
ROOM_DATA_SNAPSHOT_KEY = "shop_room_data_snapshot"
ROOM_DATA_USER_ID_KEY = "shop_room_data_snapshot_user_id"
ROOM_DATA_LOADED_AT_KEY = "shop_room_data_snapshot_loaded_at"
SHOP_DATA_CACHE_TTL_SECONDS = 30.0


def _cache_is_current(
    state: MutableMapping[str, Any],
    *,
    user_key: str,
    loaded_at_key: str,
    user_id: str,
    now: float,
) -> bool:
    loaded_at = state.get(loaded_at_key)
    if (
        not isinstance(loaded_at, (int, float))
        or isinstance(loaded_at, bool)
    ):
        return False
    age = now - loaded_at
    return (
        state.get(user_key) == user_id
        and 0 <= age < SHOP_DATA_CACHE_TTL_SECONDS
    )


def get_shop_data_snapshot(
    state: MutableMapping[str, Any],
    user_id: str,
    loader: Callable[[], Mapping[str, Any]],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """상점 공통 조회 결과를 사용자별로 짧게 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")
    current_time = monotonic() if now is None else float(now)
    snapshot = state.get(SHOP_DATA_SNAPSHOT_KEY)
    if (
        isinstance(snapshot, Mapping)
        and _cache_is_current(
            state,
            user_key=SHOP_DATA_USER_ID_KEY,
            loaded_at_key=SHOP_DATA_LOADED_AT_KEY,
            user_id=normalized_user_id,
            now=current_time,
        )
    ):
        return dict(snapshot)

    loaded = loader()
    if not isinstance(loaded, Mapping):
        raise RuntimeError("상점 조회 결과가 올바르지 않습니다.")
    stored = dict(loaded)
    state[SHOP_DATA_SNAPSHOT_KEY] = stored
    state[SHOP_DATA_USER_ID_KEY] = normalized_user_id
    state[SHOP_DATA_LOADED_AT_KEY] = current_time
    return dict(stored)


def get_room_data_snapshot(
    state: MutableMapping[str, Any],
    user_id: str,
    loader: Callable[[], Mapping[str, Any] | None],
    *,
    now: float | None = None,
) -> dict[str, Any] | None:
    """저장된 학습방 조회 결과를 사용자별로 짧게 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")
    current_time = monotonic() if now is None else float(now)
    if (
        ROOM_DATA_SNAPSHOT_KEY in state
        and _cache_is_current(
            state,
            user_key=ROOM_DATA_USER_ID_KEY,
            loaded_at_key=ROOM_DATA_LOADED_AT_KEY,
            user_id=normalized_user_id,
            now=current_time,
        )
    ):
        snapshot = state.get(ROOM_DATA_SNAPSHOT_KEY)
        return dict(snapshot) if isinstance(snapshot, Mapping) else None

    loaded = loader()
    if loaded is not None and not isinstance(loaded, Mapping):
        raise RuntimeError("학습방 조회 결과가 올바르지 않습니다.")
    stored = dict(loaded) if isinstance(loaded, Mapping) else None
    state[ROOM_DATA_SNAPSHOT_KEY] = stored
    state[ROOM_DATA_USER_ID_KEY] = normalized_user_id
    state[ROOM_DATA_LOADED_AT_KEY] = current_time
    return dict(stored) if isinstance(stored, Mapping) else None


def update_room_data_snapshot(
    state: MutableMapping[str, Any],
    room: object,
    *,
    now: float | None = None,
) -> bool:
    """저장 RPC가 반환한 학습방으로 현재 사용자 스냅샷을 갱신합니다."""

    cached_user_id = state.get(ROOM_DATA_USER_ID_KEY)
    if not isinstance(cached_user_id, str) or not isinstance(room, Mapping):
        return False
    room_user_id = room.get("user_id")
    if room_user_id is not None and str(room_user_id) != cached_user_id:
        return False
    state[ROOM_DATA_SNAPSHOT_KEY] = dict(room)
    state[ROOM_DATA_LOADED_AT_KEY] = monotonic() if now is None else float(now)
    return True


def invalidate_shop_data_snapshot(state: MutableMapping[str, Any]) -> None:
    """구매 뒤 지갑·인벤토리·상품 스냅샷을 다시 조회하게 합니다."""

    for key in (
        SHOP_DATA_SNAPSHOT_KEY,
        SHOP_DATA_USER_ID_KEY,
        SHOP_DATA_LOADED_AT_KEY,
    ):
        state.pop(key, None)


def invalidate_shop_snapshots(state: MutableMapping[str, Any]) -> None:
    """상점 테스트 변경 뒤 상점과 학습방 스냅샷을 모두 비웁니다."""

    invalidate_shop_data_snapshot(state)
    for key in (
        ROOM_DATA_SNAPSHOT_KEY,
        ROOM_DATA_USER_ID_KEY,
        ROOM_DATA_LOADED_AT_KEY,
    ):
        state.pop(key, None)


def queue_purchase_reveal(
    state: MutableMapping[str, Any],
    feedback: Mapping[str, Any],
) -> None:
    """검증된 새 구매 결과를 다음 rerun의 일회성 연출로 저장합니다."""

    if feedback.get("newly_purchased") is not True:
        return
    item_key = feedback.get("item_key")
    if not isinstance(item_key, str) or not item_key:
        raise ValueError("구매 연출 아이템 정보가 올바르지 않습니다.")
    state[PURCHASE_REVEAL_KEY] = dict(feedback)


def pop_purchase_reveal(
    state: MutableMapping[str, Any],
) -> dict[str, Any] | None:
    """구매 연출을 정확히 한 번 꺼내고 같은 세션에서 제거합니다."""

    payload = state.pop(PURCHASE_REVEAL_KEY, None)
    return dict(payload) if isinstance(payload, Mapping) else None


def queue_room_save_reveal(
    state: MutableMapping[str, Any],
    feedback: Mapping[str, Any],
) -> None:
    """서버가 확정한 학습방 저장 결과를 다음 rerun 연출로 보존합니다."""

    event_id = feedback.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("학습방 저장 연출 식별자가 올바르지 않습니다.")
    state[ROOM_SAVE_REVEAL_KEY] = dict(feedback)


def pop_room_save_reveal(
    state: MutableMapping[str, Any],
) -> dict[str, Any] | None:
    """학습방 저장 연출을 한 번 꺼내고 같은 세션에서 제거합니다."""

    payload = state.pop(ROOM_SAVE_REVEAL_KEY, None)
    return dict(payload) if isinstance(payload, Mapping) else None


def clear_shop_state(state: MutableMapping[str, Any]) -> None:
    """상점 상태만 제거하고 다른 화면과 인증 상태는 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(SHOP_STATE_PREFIX):
            state.pop(key, None)
