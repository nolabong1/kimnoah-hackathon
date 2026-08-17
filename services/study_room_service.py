from collections.abc import Iterable, Mapping
from io import BytesIO
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from models.shop import StudyRoomEquipment, StudyRoomSlot
from services.shop_catalog import SHOP_ITEMS_BY_KEY


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_ROOM_PATH = PROJECT_ROOT / "assets/study_room/base/room_default.webp"
ROOM_CANVAS_SIZE = (1600, 900)

EQUIPMENT_FIELD_SLOTS = {
    "background_item_key": StudyRoomSlot.BACKGROUND,
    "floor_item_key": StudyRoomSlot.FLOOR,
    "desk_item_key": StudyRoomSlot.DESK,
    "chair_item_key": StudyRoomSlot.CHAIR,
    "decor_left_item_key": StudyRoomSlot.DECOR_LEFT,
    "decor_right_item_key": StudyRoomSlot.DECOR_RIGHT,
    "accent_item_key": StudyRoomSlot.ACCENT,
}

SLOT_RENDER_ORDER = tuple(EQUIPMENT_FIELD_SLOTS.items())
DECOR_SLOT_CENTERS = {
    StudyRoomSlot.DECOR_LEFT: 430,
    StudyRoomSlot.DECOR_RIGHT: 1220,
}


def empty_study_room_equipment() -> dict[str, None]:
    """아직 저장된 방이 없는 사용자의 빈 슬롯 구성을 반환합니다."""

    return {field_name: None for field_name in EQUIPMENT_FIELD_SLOTS}


def extract_study_room_equipment(
    room: Mapping[str, object] | None,
) -> dict[str, str | None]:
    """저장 행에서 합성에 필요한 일곱 슬롯만 안전하게 추출합니다."""

    if room is None:
        return empty_study_room_equipment()
    payload = {
        field_name: room.get(field_name)
        for field_name in EQUIPMENT_FIELD_SLOTS
    }
    try:
        return StudyRoomEquipment.model_validate(payload).model_dump()
    except ValidationError as error:
        raise ValueError("저장된 학습방 장착 정보가 올바르지 않습니다.") from error


def validate_study_room_equipment(
    equipment: Mapping[str, object],
    owned_item_keys: Iterable[str],
) -> dict[str, str | None]:
    """보유 여부와 카탈로그 슬롯 규칙을 Python에서도 검증합니다."""

    try:
        normalized = StudyRoomEquipment.model_validate(equipment)
    except ValidationError as error:
        raise ValueError("학습방 장착 정보가 올바르지 않습니다.") from error

    owned_keys = set(owned_item_keys)
    payload = normalized.model_dump()
    for field_name, slot in EQUIPMENT_FIELD_SLOTS.items():
        item_key = payload[field_name]
        if item_key is None:
            continue
        item = SHOP_ITEMS_BY_KEY.get(item_key)
        if item is None or not item.is_active:
            raise ValueError("지원하지 않는 학습방 아이템이 포함돼 있습니다.")
        if item_key not in owned_keys:
            raise ValueError("보유하지 않은 아이템은 학습방에 장착할 수 없습니다.")
        if slot not in item.allowed_slots:
            raise ValueError("선택한 아이템을 해당 학습방 슬롯에 장착할 수 없습니다.")
    return payload


def compose_study_room_preview(
    equipment: Mapping[str, object],
    owned_item_keys: Iterable[str],
) -> bytes:
    """검증된 슬롯 구성을 로컬 에셋과 합성해 WebP 바이트로 반환합니다."""

    normalized = validate_study_room_equipment(equipment, owned_item_keys)
    with Image.open(BASE_ROOM_PATH) as base_source:
        room = base_source.convert("RGBA")
    if room.size != ROOM_CANVAS_SIZE:
        raise RuntimeError("기본 학습방 이미지 규격이 올바르지 않습니다.")

    for field_name, slot in SLOT_RENDER_ORDER:
        item_key = normalized[field_name]
        if item_key is None:
            continue
        item = SHOP_ITEMS_BY_KEY[item_key]
        overlay_path = PROJECT_ROOT / item.overlay_path
        with Image.open(overlay_path) as overlay_source:
            overlay = overlay_source.convert("RGBA")
        if overlay.size != ROOM_CANVAS_SIZE:
            raise RuntimeError("학습방 아이템 이미지 규격이 올바르지 않습니다.")
        if slot in DECOR_SLOT_CENTERS:
            overlay = _move_decoration_to_slot(overlay, slot)
        room.alpha_composite(overlay)

    output = BytesIO()
    room.convert("RGB").save(output, format="WEBP", quality=90, method=6)
    return output.getvalue()


def _move_decoration_to_slot(
    overlay: Image.Image,
    slot: StudyRoomSlot,
) -> Image.Image:
    """소품의 유효 픽셀을 좌우 고정 중심점으로 옮깁니다."""

    bounds = overlay.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("학습방 소품 이미지에서 유효한 픽셀을 찾지 못했습니다.")

    left, top, right, bottom = bounds
    decoration = overlay.crop(bounds)
    target_left = DECOR_SLOT_CENTERS[slot] - decoration.width // 2
    if (
        target_left < 0
        or target_left + decoration.width > ROOM_CANVAS_SIZE[0]
        or bottom > ROOM_CANVAS_SIZE[1]
    ):
        raise RuntimeError("학습방 소품을 고정 슬롯에 배치할 수 없습니다.")

    positioned = Image.new("RGBA", ROOM_CANVAS_SIZE, (0, 0, 0, 0))
    positioned.alpha_composite(decoration, (target_left, top))
    return positioned
