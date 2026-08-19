from typing import Any

import streamlit as st

from views.collection_view import render_shop_collection
from views.shop_view import (
    load_shop_page_data,
    render_shop_inventory,
    render_shop_load_error,
    render_shop_market,
)
from views.study_room_view import (
    load_study_room_data,
    render_study_room,
    render_study_room_load_error,
)
from views.ui_components import render_page_header


def render_shop_page(supabase, user) -> None:
    """코인 상점을 독립 페이지로 표시합니다."""

    render_page_header(
        "코인 상점",
        "학습으로 모은 코인으로 학습방 꾸미기 아이템을 구매합니다.",
    )
    loaded = _load_shop_data(supabase, user)
    if loaded is not None:
        render_shop_market(supabase, loaded)


def render_inventory_page(supabase, user) -> None:
    """사용자가 보유한 꾸미기 아이템을 독립 페이지로 표시합니다."""

    render_page_header(
        "내 아이템",
        "구매해 영구 보유한 꾸미기 아이템을 확인합니다.",
    )
    loaded = _load_shop_data(supabase, user)
    if loaded is not None:
        render_shop_inventory(loaded)


def render_study_room_page(supabase, user) -> None:
    """직접 편집할 수 있는 학습방을 독립 페이지로 표시합니다."""

    render_page_header(
        "내 학습방",
        "보유 아이템을 배치하고 나만의 학습 공간을 꾸며보세요.",
    )
    loaded = _load_shop_data(supabase, user)
    if loaded is None:
        return

    user_id = _get_user_id(user)
    if user_id is None:
        return
    try:
        saved_room = load_study_room_data(supabase, user_id)
    except Exception as error:
        render_study_room_load_error(error)
        return
    render_study_room(supabase, loaded, saved_room)


def render_collection_page(supabase, user) -> None:
    """꾸미기 아이템 수집 현황을 독립 페이지로 표시합니다."""

    render_page_header(
        "꾸미기 컬렉션",
        "전체 꾸미기 아이템의 보유·장착 상태와 수집률을 확인합니다.",
    )
    loaded = _load_shop_data(supabase, user)
    if loaded is None:
        return

    user_id = _get_user_id(user)
    if user_id is None:
        return
    try:
        saved_room = load_study_room_data(supabase, user_id)
    except Exception as error:
        render_study_room_load_error(error)
        return
    render_shop_collection(loaded, saved_room)


def _load_shop_data(supabase, user) -> dict[str, Any] | None:
    """인증 사용자 확인 후 상점 공통 데이터를 안전하게 조회합니다."""

    user_id = _get_user_id(user)
    if user_id is None:
        return None
    try:
        return load_shop_page_data(supabase, user_id)
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
