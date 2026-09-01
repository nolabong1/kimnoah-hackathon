from collections.abc import Mapping
from typing import Any

import streamlit as st

from views.collection_view import render_shop_collection
from views.shop_view import (
    load_shop_page_data,
    render_shop_load_error,
    render_shop_market,
)
from views.study_room_view import (
    load_study_room_data,
    render_study_room,
    render_study_room_load_error,
)
from views.shop_state import get_room_data_snapshot, get_shop_data_snapshot
from views.ui_components import render_page_header


SHOP_HUB_SECTION_KEY = "shop_hub_section"
SHOP_HUB_SECTION_ROOM = "room"
SHOP_HUB_SECTION_COLLECTION = "collection"
SHOP_HUB_SECTIONS = (
    SHOP_HUB_SECTION_ROOM,
    SHOP_HUB_SECTION_COLLECTION,
)
SHOP_HUB_SECTION_LABELS = {
    SHOP_HUB_SECTION_ROOM: ":material/chair: 학습방",
    SHOP_HUB_SECTION_COLLECTION: ":material/collections_bookmark: 컬렉션",
}


def render_shop_page(supabase, user) -> None:
    """코인 상점을 독립 페이지로 표시합니다."""

    render_page_header(
        "코인 상점",
        "학습으로 모은 코인으로 학습방 꾸미기 아이템을 구매합니다.",
    )
    loaded = _load_shop_data(supabase, user)
    if loaded is not None:
        render_shop_market(supabase, loaded)


def render_study_room_page(
    supabase,
    user,
    profile: Mapping[str, Any] | None = None,
) -> None:
    """학습방과 보유 현황이 합쳐진 컬렉션을 한 페이지에서 표시합니다."""

    render_page_header(
        "내 학습방",
        "방 꾸미기부터 보유 아이템과 수집 현황까지 한곳에서 관리하세요.",
    )
    selected_section = _render_shop_hub_navigation()
    loaded = _load_shop_data(supabase, user)
    if loaded is None:
        return

    user_id = _get_user_id(user)
    if user_id is None:
        return
    try:
        saved_room = get_room_data_snapshot(
            st.session_state,
            user_id,
            lambda: load_study_room_data(supabase, user_id),
        )
    except Exception as error:
        render_study_room_load_error(error)
        return

    if selected_section == SHOP_HUB_SECTION_COLLECTION:
        render_shop_collection(loaded, saved_room)
    else:
        render_study_room(
            supabase,
            loaded,
            saved_room,
            profile=profile,
        )


def normalize_shop_hub_section(value: object) -> str:
    """세션·URL에서 받은 통합 화면 값을 허용된 기본값으로 정규화합니다."""

    if isinstance(value, str) and value in SHOP_HUB_SECTIONS:
        return value
    return SHOP_HUB_SECTION_ROOM


def _render_shop_hub_navigation() -> str:
    """통합 학습방에서 한 영역만 선택해 렌더링하도록 전환기를 표시합니다."""

    widget_options: dict[str, str] = {}
    if SHOP_HUB_SECTION_KEY in st.session_state:
        normalized = normalize_shop_hub_section(
            st.session_state.get(SHOP_HUB_SECTION_KEY)
        )
        if st.session_state.get(SHOP_HUB_SECTION_KEY) != normalized:
            st.session_state[SHOP_HUB_SECTION_KEY] = normalized
    else:
        widget_options["default"] = SHOP_HUB_SECTION_ROOM

    selected = st.segmented_control(
        "학습방 관리 메뉴",
        options=SHOP_HUB_SECTIONS,
        required=True,
        format_func=lambda section: SHOP_HUB_SECTION_LABELS[section],
        key=SHOP_HUB_SECTION_KEY,
        width="stretch",
        bind="query-params",
        label_visibility="collapsed",
        **widget_options,
    )
    return normalize_shop_hub_section(selected)


def _load_shop_data(supabase, user) -> dict[str, Any] | None:
    """인증 사용자 확인 후 상점 공통 데이터를 안전하게 조회합니다."""

    user_id = _get_user_id(user)
    if user_id is None:
        return None
    try:
        return get_shop_data_snapshot(
            st.session_state,
            user_id,
            lambda: load_shop_page_data(supabase, user_id),
        )
    except Exception as error:
        render_shop_load_error(error)
        return None


def _get_user_id(user) -> str | None:
    """페이지 조회에 사용할 인증 사용자 ID를 반환합니다."""

    user_id = getattr(user, "id", None)
    if user_id is None:
        st.error("로그인 정보를 확인할 수 없습니다. 다시 로그인해주세요.")
        return None
    return str(user_id)
