from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from models.shop import ShopItemCategory
from services.shop_catalog import SHOP_ITEMS_BY_KEY
from services.shop_repository import (
    get_shop_items,
    get_user_coin_wallet,
    get_user_inventory,
    purchase_shop_item,
)
from views.shop_state import (
    CATEGORY_FILTER_KEY,
    PURCHASE_IN_PROGRESS_KEY,
    SUCCESS_MESSAGE_KEY,
)
from views.ui_components import MetricItem, render_empty_state, render_metric_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATEGORY_LABELS = {
    ShopItemCategory.BACKGROUND.value: "배경",
    ShopItemCategory.FLOOR.value: "바닥",
    ShopItemCategory.DESK.value: "책상",
    ShopItemCategory.CHAIR.value: "의자",
    ShopItemCategory.DECORATION.value: "장식",
    ShopItemCategory.ACCENT.value: "포인트",
}
RARITY_LABELS = {
    "common": "일반",
    "uncommon": "고급",
    "rare": "희귀",
}
CATEGORY_ICONS = {
    ShopItemCategory.BACKGROUND.value: ":material/wallpaper:",
    ShopItemCategory.FLOOR.value: ":material/texture:",
    ShopItemCategory.DESK.value: ":material/desk:",
    ShopItemCategory.CHAIR.value: ":material/chair:",
    ShopItemCategory.DECORATION.value: ":material/potted_plant:",
    ShopItemCategory.ACCENT.value: ":material/pets:",
}


def load_shop_page_data(supabase, user_id: str) -> dict[str, Any]:
    """인증 사용자의 지갑·상점·인벤토리를 한 번씩 조회합니다."""

    return {
        "wallet": get_user_coin_wallet(supabase, user_id),
        "items": get_shop_items(supabase),
        "inventory": get_user_inventory(supabase, user_id),
    }


def render_shop_load_error(error: Exception) -> None:
    """원시 서버 응답을 노출하지 않고 상점 초기화 문제를 안내합니다."""

    raw_message = str(error)
    if any(
        marker in raw_message
        for marker in (
            "shop_items",
            "user_inventory",
            "user_coin_wallets",
            "PGRST202",
            "PGRST205",
        )
    ):
        st.error(
            "코인 상점 데이터베이스 설정을 확인할 수 없습니다. "
            "필수 Supabase 상점 마이그레이션이 적용됐는지 확인해주세요."
        )
        return
    st.error("코인 상점 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")


def render_shop_market(
    supabase,
    shop_data: dict[str, Any],
) -> None:
    """활성 상품을 필터 가능한 카드로 보여주고 구매를 연결합니다."""

    wallet = shop_data["wallet"]
    items = shop_data["items"]
    inventory = shop_data["inventory"]
    owned_keys = {entry["item_key"] for entry in inventory}

    if SUCCESS_MESSAGE_KEY in st.session_state:
        st.success(st.session_state.pop(SUCCESS_MESSAGE_KEY))

    render_metric_row(
        [
            MetricItem(
                "보유 코인",
                f"{wallet['balance']}개",
                icon=":material/toll:",
            ),
            MetricItem(
                "누적 획득",
                f"{wallet['lifetime_earned']}개",
                icon=":material/add_circle:",
            ),
            MetricItem(
                "누적 사용",
                f"{wallet['lifetime_spent']}개",
                icon=":material/shopping_bag:",
            ),
        ]
    )
    st.caption(
        "코인은 학습 보상과 도전과제로 모을 수 있으며 꾸미기 아이템 구매에만 사용됩니다."
    )

    filter_options = ["전체", *CATEGORY_LABELS.values()]
    selected_category = st.selectbox(
        "아이템 카테고리",
        options=filter_options,
        key=CATEGORY_FILTER_KEY,
        persist_state="session",
    )
    visible_items = filter_shop_items(items, selected_category)

    if not visible_items:
        render_empty_state(
            "표시할 상점 아이템이 없습니다",
            "다른 카테고리를 선택하거나 상점 카탈로그를 확인해주세요.",
            icon=":material/storefront:",
        )
        return

    columns = st.columns(3, gap="medium")
    for index, item in enumerate(visible_items):
        with columns[index % 3]:
            _render_shop_item_card(
                supabase=supabase,
                item=item,
                balance=wallet["balance"],
                is_owned=item["item_key"] in owned_keys,
            )


def render_shop_inventory(shop_data: dict[str, Any]) -> None:
    """사용자가 영구 소유한 아이템과 구매 정보를 표시합니다."""

    items_by_key = {
        item["item_key"]: item
        for item in shop_data["items"]
    }
    inventory = shop_data["inventory"]

    if not inventory:
        render_empty_state(
            "아직 보유한 아이템이 없습니다",
            "상점에서 첫 꾸미기 아이템을 구매해보세요.",
            icon=":material/inventory_2:",
        )
        return

    st.caption(
        f"구매한 아이템 {len(inventory)}개를 보유하고 있습니다. "
        "학습방 화면에서 원하는 슬롯에 장착할 수 있습니다."
    )
    missing_item_count = sum(
        entry["item_key"] not in items_by_key
        for entry in inventory
    )
    if missing_item_count:
        st.warning(
            "현재 카탈로그에서 확인할 수 없는 보유 아이템이 있어 일부를 숨겼습니다."
        )

    visible_inventory = [
        entry
        for entry in inventory
        if entry["item_key"] in items_by_key
    ]
    columns = st.columns(3, gap="medium")
    for index, inventory_item in enumerate(visible_inventory):
        item = items_by_key[inventory_item["item_key"]]
        with columns[index % 3]:
            _render_inventory_item_card(item, inventory_item)


def filter_shop_items(
    items: list[dict],
    selected_category: str,
) -> list[dict]:
    """한국어 필터 선택에 해당하는 아이템만 기존 순서대로 반환합니다."""

    if selected_category == "전체":
        return list(items)

    category_by_label = {
        label: category
        for category, label in CATEGORY_LABELS.items()
    }
    selected_value = category_by_label.get(selected_category)
    if selected_value is None:
        return []
    return [
        item
        for item in items
        if item.get("category") == selected_value
    ]


@st.dialog("꾸미기 아이템 구매")
def _show_purchase_dialog(
    supabase,
    item: dict,
    balance: int,
) -> None:
    """코인을 사용하기 전에 가격과 구매 후 잔액을 확인합니다."""

    st.markdown(f"### {item['name_ko']}")
    st.write(f"**{item['price']} 코인**을 사용해 이 아이템을 구매할까요?")
    st.caption(
        f"현재 {balance} 코인 · 구매 후 {balance - item['price']} 코인"
    )
    st.info("구매한 아이템은 인벤토리에 영구 보관됩니다.")

    purchase_running = bool(
        st.session_state.get(PURCHASE_IN_PROGRESS_KEY, False)
    )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "취소",
            key=f"shop_cancel_purchase_{item['item_key']}",
            disabled=purchase_running,
        ):
            st.rerun()

        if st.button(
            "구매 확정",
            key=f"shop_confirm_purchase_{item['item_key']}",
            type="primary",
            icon=":material/shopping_cart_checkout:",
            disabled=purchase_running,
        ):
            st.session_state[PURCHASE_IN_PROGRESS_KEY] = True
            try:
                with st.spinner("아이템을 안전하게 구매하고 있습니다..."):
                    message = execute_shop_purchase(supabase, item)
                st.session_state[SUCCESS_MESSAGE_KEY] = message
                st.rerun()
            except Exception as error:
                st.error(_friendly_purchase_error(error))
            finally:
                st.session_state.pop(PURCHASE_IN_PROGRESS_KEY, None)


def execute_shop_purchase(supabase, item: dict) -> str:
    """구매 RPC를 한 번 호출하고 사용자에게 보여줄 결과 문구를 만듭니다."""

    result = purchase_shop_item(supabase, item["item_key"])
    if result["already_owned"]:
        return "이미 보유한 아이템입니다. 코인은 차감되지 않았습니다."
    return (
        f"'{item['name_ko']}' 구매를 완료했습니다. "
        f"남은 코인은 {result['balance']}개입니다."
    )


def _render_shop_item_card(
    supabase,
    item: dict,
    balance: int,
    is_owned: bool,
) -> None:
    """상점 아이템 한 건을 승인된 정보 순서의 카드로 표시합니다."""

    with st.container(border=True):
        render_shop_item_visual(item)
        st.caption(
            f"{RARITY_LABELS[item['rarity']]} · "
            f"{CATEGORY_LABELS[item['category']]}"
        )
        st.markdown(f"### {item['name_ko']}")
        st.markdown(f"**{item['price']} 코인**")

        if is_owned:
            st.success("보유 중", icon=":material/check_circle:")
            st.button(
                "이미 보유한 아이템",
                key=f"shop_owned_{item['item_key']}",
                width="stretch",
                disabled=True,
            )
            return

        can_afford = balance >= item["price"]
        if not can_afford:
            st.caption(f"코인 {item['price'] - balance}개가 더 필요합니다.")
        else:
            st.caption("현재 보유 코인으로 구매할 수 있습니다.")

        if st.button(
            "구매하기",
            key=f"shop_buy_{item['item_key']}",
            type="primary" if can_afford else "secondary",
            icon=":material/shopping_cart:",
            width="stretch",
            disabled=not can_afford,
            help=(
                None
                if can_afford
                else "코인이 부족해 아직 구매할 수 없습니다."
            ),
        ):
            _show_purchase_dialog(supabase, item, balance)


def _render_inventory_item_card(
    item: dict,
    inventory_item: dict,
) -> None:
    """보유 아이템 한 건의 가격 스냅샷과 획득일을 표시합니다."""

    with st.container(border=True):
        render_shop_item_visual(item)
        st.caption(
            f"{RARITY_LABELS[item['rarity']]} · "
            f"{CATEGORY_LABELS[item['category']]}"
        )
        st.markdown(f"### {item['name_ko']}")
        st.success("보유 중", icon=":material/inventory_2:")
        st.caption(
            f"구매 가격 {inventory_item['price_paid']} 코인 · "
            f"획득일 {_format_acquired_date(inventory_item['acquired_at'])}"
        )


def render_shop_item_visual(item: dict) -> None:
    """승인된 로컬 썸네일만 표시하고 없으면 카테고리 아이콘을 사용합니다."""

    thumbnail_path = _get_approved_thumbnail_path(item)
    with st.container(
        height=150,
        horizontal_alignment="center",
        vertical_alignment="center",
    ):
        if thumbnail_path is not None:
            st.image(str(thumbnail_path), width=138)
        else:
            st.markdown(f"## {CATEGORY_ICONS[item['category']]}")
            st.caption("아이템 이미지 준비 중")


def _get_approved_thumbnail_path(item: dict) -> Path | None:
    """코드 카탈로그와 경로가 같은 실제 에셋만 로컬에서 읽습니다."""

    definition = SHOP_ITEMS_BY_KEY.get(item.get("item_key"))
    if definition is None:
        return None
    if item.get("thumbnail_path") != definition.thumbnail_path:
        return None
    candidate = PROJECT_ROOT / definition.thumbnail_path
    return candidate if candidate.is_file() else None


def _format_acquired_date(value: str | datetime) -> str:
    """인벤토리 획득 시각을 간결한 날짜로 표시합니다."""

    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y-%m-%d")


def _friendly_purchase_error(error: Exception) -> str:
    """구매 RPC의 알려진 오류만 안전한 한국어 메시지로 변환합니다."""

    raw_message = str(error)
    for message in (
        "코인이 부족합니다.",
        "구매할 수 있는 상점 아이템을 찾을 수 없습니다.",
        "코인 지갑을 찾을 수 없습니다.",
        "로그인이 필요합니다.",
    ):
        if message in raw_message:
            return message
    if any(
        marker in raw_message
        for marker in ("purchase_shop_item", "PGRST202")
    ):
        return (
            "상점 구매 기능이 아직 데이터베이스에 적용되지 않았습니다. "
            "필수 Supabase 마이그레이션을 확인해주세요."
        )
    return "아이템 구매를 완료하지 못했습니다. 잠시 후 다시 시도해주세요."
