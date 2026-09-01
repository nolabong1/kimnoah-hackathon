from collections.abc import Mapping, MutableMapping
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
