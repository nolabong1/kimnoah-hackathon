from typing import Any

import streamlit as st

from services.collection_service import (
    CollectionSummary,
    build_collection_summary,
)
from views.collection_gallery_component import (
    build_collection_gallery_items,
    render_collection_gallery,
)
from views.shop_state import (
    COLLECTION_CATEGORY_FILTER_KEY,
    COLLECTION_STATUS_FILTER_KEY,
)
from views.shop_view import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    RARITY_LABELS,
    filter_shop_items,
    render_shop_item_visual,
)
from views.ui_components import MetricItem, render_empty_state, render_metric_row


COLLECTION_STATUS_ALL = "all"
COLLECTION_STATUS_OWNED = "owned"
COLLECTION_STATUS_EQUIPPED = "equipped"
COLLECTION_STATUS_UNOWNED = "unowned"
COLLECTION_STATUS_OPTIONS = (
    COLLECTION_STATUS_ALL,
    COLLECTION_STATUS_OWNED,
    COLLECTION_STATUS_EQUIPPED,
    COLLECTION_STATUS_UNOWNED,
)
COLLECTION_STATUS_LABELS = {
    COLLECTION_STATUS_ALL: "전체",
    COLLECTION_STATUS_OWNED: "보유",
    COLLECTION_STATUS_EQUIPPED: "장착 중",
    COLLECTION_STATUS_UNOWNED: "미보유",
}


def render_shop_collection(
    shop_data: dict[str, Any],
    saved_room: dict | None,
) -> None:
    """전체 꾸미기 아이템과 사용자의 수집·장착 상태를 표시합니다."""

    items = shop_data["items"]
    inventory = shop_data["inventory"]
    summary = build_collection_summary(items, inventory, saved_room)

    if not items:
        render_empty_state(
            "표시할 컬렉션이 없습니다",
            "활성 상점 아이템이 추가되면 이곳에 수집 현황이 표시됩니다.",
            icon=":material/collections_bookmark:",
        )
        return

    st.subheader("꾸미기 컬렉션")
    st.caption(
        "상점 아이템을 모아 나만의 학습방 컬렉션을 완성해보세요. "
        "기본 방은 수집률에 포함되지 않습니다."
    )
    render_metric_row(
        [
            MetricItem(
                "수집한 아이템",
                f"{summary.owned_count}/{summary.total_count}개",
                icon=":material/inventory_2:",
            ),
            MetricItem(
                "전체 수집률",
                f"{summary.completion_percent}%",
                icon=":material/donut_large:",
            ),
            MetricItem(
                "현재 장착",
                f"{summary.equipped_count}개",
                icon=":material/chair:",
            ),
        ]
    )
    st.progress(
        summary.completion_percent / 100,
        text=(
            f"전체 진행 {summary.owned_count}/{summary.total_count} · "
            f"{summary.completion_percent}%"
        ),
    )

    _render_category_progress(summary)

    st.markdown("### 아이템 보유 현황")
    selected_status = st.segmented_control(
        "보유 상태",
        options=COLLECTION_STATUS_OPTIONS,
        default=COLLECTION_STATUS_ALL,
        required=True,
        format_func=lambda status: COLLECTION_STATUS_LABELS[status],
        key=COLLECTION_STATUS_FILTER_KEY,
        width="stretch",
        persist_state="session",
    )
    selected_category = st.selectbox(
        "컬렉션 카테고리",
        options=["전체", *CATEGORY_LABELS.values()],
        key=COLLECTION_CATEGORY_FILTER_KEY,
        persist_state="session",
    )
    category_items = filter_shop_items(items, selected_category)
    visible_items = filter_collection_items_by_status(
        category_items,
        owned_keys=summary.owned_keys,
        equipped_keys=summary.equipped_keys,
        selected_status=selected_status,
    )
    if not visible_items:
        render_empty_state(
            "선택한 조건에 아이템이 없습니다",
            "다른 보유 상태나 카테고리를 선택해주세요.",
            icon=":material/category:",
        )
        return

    gallery_items = build_collection_gallery_items(
        visible_items,
        owned_keys=summary.owned_keys,
        equipped_keys=summary.equipped_keys,
    )
    if render_collection_gallery(
        gallery_items,
        key=(
            "shop_collection_gallery_"
            f"{selected_status}_{selected_category}"
        ),
    ):
        st.caption(
            "아이템 카드를 선택하면 오른쪽에서 수집 상태와 이용 방법을 "
            "확인할 수 있습니다. 구매와 장착은 상점·학습방에서 진행합니다."
        )
        return

    columns = st.columns(3, gap="medium")
    for index, item in enumerate(visible_items):
        with columns[index % 3]:
            _render_collection_item_card(item, summary)


def filter_collection_items_by_status(
    items: list[dict],
    *,
    owned_keys: frozenset[str] | set[str],
    equipped_keys: frozenset[str] | set[str],
    selected_status: object,
) -> list[dict]:
    """보유·장착 상태에 해당하는 컬렉션 아이템을 기존 순서대로 반환합니다."""

    if selected_status == COLLECTION_STATUS_ALL:
        return list(items)
    if selected_status == COLLECTION_STATUS_OWNED:
        return [item for item in items if item.get("item_key") in owned_keys]
    if selected_status == COLLECTION_STATUS_EQUIPPED:
        return [
            item for item in items if item.get("item_key") in equipped_keys
        ]
    if selected_status == COLLECTION_STATUS_UNOWNED:
        return [item for item in items if item.get("item_key") not in owned_keys]
    return []


def _render_category_progress(summary: CollectionSummary) -> None:
    """여섯 카테고리의 수집 진행도를 세 열 카드로 표시합니다."""

    st.markdown("### 카테고리별 수집")
    columns = st.columns(3, gap="medium")
    for index, progress in enumerate(summary.category_progress):
        with columns[index % 3]:
            with st.container(border=True):
                st.markdown(
                    f"**{CATEGORY_ICONS[progress.category]} "
                    f"{CATEGORY_LABELS[progress.category]}**"
                )
                st.progress(
                    progress.completion_percent / 100,
                    text=(
                        f"{progress.owned_count}/{progress.total_count} · "
                        f"{progress.completion_percent}%"
                    ),
                )


def _render_collection_item_card(
    item: dict,
    summary: CollectionSummary,
) -> None:
    """아이템 한 건의 잠금·보유·장착 상태를 일관된 카드로 표시합니다."""

    item_key = item["item_key"]
    is_owned = item_key in summary.owned_keys
    is_equipped = item_key in summary.equipped_keys

    with st.container(border=True):
        st.caption(
            "장착 중"
            if is_equipped
            else ("수집 완료" if is_owned else "잠긴 아이템")
        )
        render_shop_item_visual(item)
        st.caption(
            f"{RARITY_LABELS[item['rarity']]} · "
            f"{CATEGORY_LABELS[item['category']]}"
        )
        st.markdown(f"### {item['name_ko']}")

        if is_equipped:
            st.success("현재 학습방에 장착 중", icon=":material/check_circle:")
        elif is_owned:
            st.success("보유 중", icon=":material/inventory_2:")
        else:
            st.caption(f"상점 가격 {item['price']} 코인 · 아직 수집하지 않음")
