from collections.abc import Mapping
from typing import Any

import streamlit as st

from models.shop import StudyRoomSlot
from services.shop_repository import (
    get_user_study_room,
    save_user_study_room,
)
from services.study_room_service import (
    EQUIPMENT_FIELD_SLOTS,
    TRANSFORMABLE_FIELD_SLOTS,
    build_study_room_editor_scene,
    empty_study_room_transforms,
    extract_study_room_equipment,
    extract_study_room_transforms,
    validate_study_room_equipment,
    validate_study_room_transforms,
)
from views.error_feedback import render_unexpected_error
from views.shop_state import (
    ROOM_EDITOR_COMPONENT_KEY,
    ROOM_EQUIPMENT_DRAFT_KEY,
    ROOM_SAVE_IN_PROGRESS_KEY,
    ROOM_SAVED_SOURCE_KEY,
    ROOM_SUCCESS_MESSAGE_KEY,
    ROOM_TRANSFORMS_DRAFT_KEY,
)
from views.study_room_editor_component import render_study_room_editor


SLOT_LABELS = {
    StudyRoomSlot.BACKGROUND: "벽지",
    StudyRoomSlot.FLOOR: "바닥",
    StudyRoomSlot.DESK: "책상",
    StudyRoomSlot.CHAIR: "의자",
    StudyRoomSlot.DECOR_LEFT: "왼쪽 소품",
    StudyRoomSlot.DECOR_RIGHT: "오른쪽 소품",
    StudyRoomSlot.ACCENT: "포인트",
}


def load_study_room_data(supabase, user_id: str) -> dict | None:
    """인증 사용자의 저장된 학습방을 한 번 조회합니다."""

    return get_user_study_room(supabase, user_id)


def render_study_room(
    supabase,
    shop_data: dict[str, Any],
    saved_room: dict | None,
) -> None:
    """보유 아이템으로 방을 미리 보고 명시적으로 저장하게 합니다."""

    if ROOM_SUCCESS_MESSAGE_KEY in st.session_state:
        st.success(st.session_state.pop(ROOM_SUCCESS_MESSAGE_KEY))

    items = shop_data["items"]
    inventory = shop_data["inventory"]
    owned_keys = {entry["item_key"] for entry in inventory}
    items_by_key = {item["item_key"]: item for item in items}
    saved_equipment = extract_study_room_equipment(saved_room)
    saved_transforms = extract_study_room_transforms(saved_room)
    saved_source = (
        "empty"
        if saved_room is None
        else str(saved_room.get("updated_at", "saved"))
    )
    if st.session_state.get(ROOM_SAVED_SOURCE_KEY) != saved_source:
        st.session_state[ROOM_SAVED_SOURCE_KEY] = saved_source
        st.session_state[ROOM_TRANSFORMS_DRAFT_KEY] = saved_transforms
        st.session_state[ROOM_EQUIPMENT_DRAFT_KEY] = saved_equipment
        for field_name, slot in EQUIPMENT_FIELD_SLOTS.items():
            st.session_state[f"shop_room_slot_{slot.value}"] = (
                saved_equipment[field_name]
            )
    st.session_state.setdefault(
        ROOM_TRANSFORMS_DRAFT_KEY,
        saved_transforms,
    )
    st.session_state.setdefault(
        ROOM_EQUIPMENT_DRAFT_KEY,
        saved_equipment,
    )

    preview_column, editor_column = st.columns(
        [1.65, 1],
        gap="large",
        vertical_alignment="top",
    )

    with editor_column:
        st.subheader("꾸미기 설정")
        st.caption("구매해 보유한 아이템만 장착할 수 있습니다.")
        selected_equipment: dict[str, str | None] = {}

        for field_name, slot in EQUIPMENT_FIELD_SLOTS.items():
            options = _slot_options(items, owned_keys, slot)
            widget_key = f"shop_room_slot_{slot.value}"
            if widget_key not in st.session_state:
                saved_value = saved_equipment[field_name]
                st.session_state[widget_key] = (
                    saved_value if saved_value in options else None
                )
            selected_equipment[field_name] = st.selectbox(
                SLOT_LABELS[slot],
                options=options,
                format_func=lambda value, lookup=items_by_key: (
                    "비어 있음"
                    if value is None
                    else lookup[value]["name_ko"]
                ),
                key=widget_key,
                persist_state="session",
            )

        selected_transforms = validate_study_room_transforms(
            st.session_state.get(ROOM_TRANSFORMS_DRAFT_KEY)
        )
        previous_equipment = st.session_state.get(
            ROOM_EQUIPMENT_DRAFT_KEY,
            saved_equipment,
        )
        default_transforms = empty_study_room_transforms()
        for field_name, slot in TRANSFORMABLE_FIELD_SLOTS.items():
            if selected_equipment[field_name] != previous_equipment.get(
                field_name
            ):
                selected_transforms[slot.value] = default_transforms[slot.value]
        st.session_state[ROOM_TRANSFORMS_DRAFT_KEY] = selected_transforms
        st.session_state[ROOM_EQUIPMENT_DRAFT_KEY] = selected_equipment.copy()

        validation_error = _equipment_error(
            selected_equipment,
            owned_keys,
        )
        if validation_error is not None:
            st.warning(validation_error)

        has_changes = (
            selected_equipment != saved_equipment
            or selected_transforms != saved_transforms
        )
        save_running = bool(
            st.session_state.get(ROOM_SAVE_IN_PROGRESS_KEY, False)
        )
        if st.button(
            "학습방 저장하기",
            key="shop_room_save",
            type="primary",
            icon=":material/save:",
            width="stretch",
            disabled=(
                save_running
                or validation_error is not None
                or not has_changes
            ),
            help=(
                "변경된 장착 구성이 없습니다."
                if not has_changes and validation_error is None
                else None
            ),
        ):
            st.session_state[ROOM_SAVE_IN_PROGRESS_KEY] = True
            try:
                with st.spinner("학습방을 안전하게 저장하고 있습니다..."):
                    execute_study_room_save(
                        supabase,
                        selected_equipment,
                        owned_keys,
                        selected_transforms,
                    )
                st.session_state[ROOM_SUCCESS_MESSAGE_KEY] = (
                    "학습방 구성을 저장했습니다."
                )
                st.rerun()
            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="study_room.save",
                    user_message=_friendly_room_save_error(error),
                )
            finally:
                st.session_state.pop(ROOM_SAVE_IN_PROGRESS_KEY, None)

    with preview_column:
        st.subheader("내 학습방")
        st.caption(
            "가구를 직접 움직인 결과는 저장 버튼을 눌러야 보존됩니다."
        )
        with st.container(border=True):
            if validation_error is None:
                try:
                    scene = build_study_room_editor_scene(
                        selected_equipment,
                        owned_keys,
                        selected_transforms,
                    )
                    render_study_room_editor(
                        scene,
                        key=ROOM_EDITOR_COMPONENT_KEY,
                        on_transforms_change=(
                            _capture_study_room_editor_transforms
                        ),
                    )
                except Exception as error:
                    render_unexpected_error(
                        error,
                        operation="study_room.build_preview",
                        user_message=(
                            "학습방 미리보기를 만들지 못했습니다. 로컬 "
                            "에셋 파일을 확인해주세요."
                        ),
                    )
            else:
                st.info("장착 구성을 확인하면 미리보기가 표시됩니다.")

        equipped_count = sum(
            item_key is not None
            for item_key in selected_equipment.values()
        )
        st.caption(f"현재 선택한 슬롯 {equipped_count}/7개")


def execute_study_room_save(
    supabase,
    equipment: dict[str, str | None],
    owned_item_keys: set[str],
    transforms: object | None = None,
) -> dict:
    """Python 검증 후 학습방 저장 RPC를 정확히 한 번 호출합니다."""

    normalized = validate_study_room_equipment(
        equipment,
        owned_item_keys,
    )
    normalized_transforms = validate_study_room_transforms(transforms)
    return save_user_study_room(
        supabase,
        normalized,
        normalized_transforms,
    )


def _capture_study_room_editor_transforms() -> None:
    """CCv2가 조작 종료 시 보낸 변형값을 학습방 초안에 반영합니다."""

    component_state = st.session_state.get(ROOM_EDITOR_COMPONENT_KEY)
    if not isinstance(component_state, Mapping):
        return
    raw_transforms = component_state.get("transforms")
    try:
        normalized = validate_study_room_transforms(raw_transforms)
    except ValueError:
        return
    st.session_state[ROOM_TRANSFORMS_DRAFT_KEY] = normalized


def _slot_options(
    items: list[dict],
    owned_keys: set[str],
    slot: StudyRoomSlot,
) -> list[str | None]:
    """상점 정렬을 유지하며 슬롯에 맞는 보유 아이템만 반환합니다."""

    return [
        None,
        *[
            item["item_key"]
            for item in items
            if item["item_key"] in owned_keys
            and slot.value in item["allowed_slots"]
        ],
    ]


def _equipment_error(
    equipment: dict[str, str | None],
    owned_keys: set[str],
) -> str | None:
    """미리보기와 저장을 막아야 하는 선택 오류만 반환합니다."""

    try:
        validate_study_room_equipment(equipment, owned_keys)
    except ValueError as error:
        return str(error)
    return None


def render_study_room_load_error(error: Exception) -> None:
    """학습방 마이그레이션 누락과 일반 조회 실패를 구분해 안내합니다."""

    raw_message = str(error)
    if any(
        marker in raw_message
        for marker in (
            "user_study_rooms",
            "item_transforms",
            "PGRST202",
            "PGRST205",
        )
    ):
        user_message = (
            "학습방 데이터베이스 설정이 아직 적용되지 않았습니다. "
            "Supabase에서 학습방 마이그레이션을 실행해주세요."
        )
    else:
        user_message = (
            "학습방을 불러오지 못했습니다. 잠시 후 다시 시도해주세요."
        )
    render_unexpected_error(
        error,
        operation="study_room.load",
        user_message=user_message,
    )


def _friendly_room_save_error(error: Exception) -> str:
    """저장 RPC의 알려진 실패를 안전한 한국어 메시지로 바꿉니다."""

    raw_message = str(error)
    for message in (
        "같은 소품을 좌우 슬롯에 동시에 장착할 수 없습니다.",
        "보유하지 않은 아이템은 학습방에 장착할 수 없습니다.",
        "선택한 아이템을 해당 학습방 슬롯에 장착할 수 없습니다.",
        "보유하지 않았거나 슬롯에 맞지 않는 아이템입니다",
        "로그인이 필요합니다.",
    ):
        if message in raw_message:
            return message
    if any(
        marker in raw_message
        for marker in (
            "save_user_study_room",
            "item_transforms",
            "PGRST202",
        )
    ):
        return (
            "학습방 저장 기능이 아직 데이터베이스에 적용되지 않았습니다. "
            "필수 Supabase 마이그레이션을 확인해주세요."
        )
    return "학습방을 저장하지 못했습니다. 잠시 후 다시 시도해주세요."
