from collections.abc import MutableMapping
from typing import Any


SHOP_STATE_PREFIX = "shop_"
SUCCESS_MESSAGE_KEY = "shop_success_message"
PURCHASE_IN_PROGRESS_KEY = "shop_purchase_in_progress"
CATEGORY_FILTER_KEY = "shop_category_filter"
COLLECTION_CATEGORY_FILTER_KEY = "shop_collection_category_filter"
ROOM_SAVE_IN_PROGRESS_KEY = "shop_room_save_in_progress"
ROOM_SUCCESS_MESSAGE_KEY = "shop_room_success_message"


def clear_shop_state(state: MutableMapping[str, Any]) -> None:
    """상점 상태만 제거하고 다른 화면과 인증 상태는 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(SHOP_STATE_PREFIX):
            state.pop(key, None)
