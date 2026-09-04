import base64
from collections.abc import Iterable, Mapping
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import ValidationError

from models.shop import (
    STUDY_ROOM_CANVAS_HEIGHT,
    STUDY_ROOM_CANVAS_WIDTH,
    STUDY_ROOM_TRANSFORM_LIMITS,
    StudyRoomEquipment,
    StudyRoomItemTransform,
    StudyRoomSlot,
    StudyRoomTransforms,
)
from services.shop_catalog import SHOP_ITEMS_BY_KEY


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_ROOM_PATH = PROJECT_ROOT / "assets/study_room/base/room_default.webp"
ROOM_CANVAS_SIZE = (STUDY_ROOM_CANVAS_WIDTH, STUDY_ROOM_CANVAS_HEIGHT)

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
TRANSFORMABLE_FIELD_SLOTS = {
    field_name: slot
    for field_name, slot in EQUIPMENT_FIELD_SLOTS.items()
    if slot not in (StudyRoomSlot.BACKGROUND, StudyRoomSlot.FLOOR)
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


def empty_study_room_transforms() -> dict[str, dict[str, object]]:
    """직접 편집 전의 다섯 슬롯 기본 변형값을 반환합니다."""

    return StudyRoomTransforms().model_dump(mode="json")


def extract_study_room_transforms(
    room: Mapping[str, object] | None,
) -> dict[str, dict[str, object]]:
    """저장된 JSON 변형값을 누락된 기본값까지 채워 안전하게 읽습니다."""

    raw_transforms = {} if room is None else room.get("item_transforms", {})
    return validate_study_room_transforms(raw_transforms)


def validate_study_room_transforms(
    transforms: object | None,
) -> dict[str, dict[str, object]]:
    """직접 조작 결과의 슬롯·위치·크기·회전 범위를 검증합니다."""

    try:
        normalized = StudyRoomTransforms.model_validate(transforms or {})
    except ValidationError as error:
        raise ValueError("학습방 가구 배치 정보가 올바르지 않습니다.") from error
    return normalized.model_dump(mode="json")


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
    transforms: object | None = None,
) -> bytes:
    """검증된 슬롯 구성을 로컬 에셋과 합성해 WebP 바이트로 반환합니다."""

    normalized = validate_study_room_equipment(equipment, owned_item_keys)
    normalized_transforms = validate_study_room_transforms(transforms)
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
        if field_name in TRANSFORMABLE_FIELD_SLOTS:
            overlay = _apply_item_transform(
                overlay,
                normalized_transforms[slot.value],
            )
        room.alpha_composite(overlay)

    output = BytesIO()
    room.convert("RGB").save(output, format="WEBP", quality=90, method=6)
    return output.getvalue()


def build_study_room_editor_scene(
    equipment: Mapping[str, object],
    owned_item_keys: Iterable[str],
    transforms: object | None = None,
) -> dict[str, object]:
    """브라우저 직접 편집기에 필요한 배경과 투명 에셋 레이어를 만듭니다."""

    normalized = validate_study_room_equipment(equipment, owned_item_keys)
    normalized_transforms = validate_study_room_transforms(transforms)
    base_image = _build_fixed_room_data_url(
        normalized["background_item_key"],
        normalized["floor_item_key"],
    )
    layers: list[dict[str, object]] = []
    for field_name, slot in TRANSFORMABLE_FIELD_SLOTS.items():
        item_key = normalized[field_name]
        if item_key is None:
            continue
        source, bounds = _cropped_overlay_data(item_key)
        left, top, right, bottom = bounds
        if slot in DECOR_SLOT_CENTERS:
            left = DECOR_SLOT_CENTERS[slot] - (right - left) // 2
        item = SHOP_ITEMS_BY_KEY[item_key]
        layers.append(
            {
                "slot": slot.value,
                "item_key": item.item_key,
                "label": item.name_ko,
                "source": source,
                "base_x": left,
                "base_y": top,
                "width": right - left,
                "height": bottom - top,
            }
        )
    return {
        "canvas_width": ROOM_CANVAS_SIZE[0],
        "canvas_height": ROOM_CANVAS_SIZE[1],
        "transform_limits": {
            name: list(bounds)
            for name, bounds in STUDY_ROOM_TRANSFORM_LIMITS.items()
        },
        "base_image": base_image,
        "layers": layers,
        "transforms": normalized_transforms,
    }


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


def _apply_item_transform(
    overlay: Image.Image,
    transform_payload: Mapping[str, object],
) -> Image.Image:
    """에셋 중심을 유지하며 이동·크기·회전·좌우 반전을 적용합니다."""

    transform = StudyRoomItemTransform.model_validate(transform_payload)
    bounds = overlay.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("학습방 아이템 이미지에서 유효한 영역을 찾지 못했습니다.")

    left, top, right, bottom = bounds
    item = overlay.crop(bounds)
    if transform.flip_horizontal:
        item = ImageOps.mirror(item)
    if transform.scale != 100:
        scale_ratio = transform.scale / 100
        resized_size = (
            max(1, round(item.width * scale_ratio)),
            max(1, round(item.height * scale_ratio)),
        )
        item = item.resize(resized_size, Image.Resampling.LANCZOS)
    if transform.rotation:
        item = item.rotate(
            -transform.rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )

    center_x = (left + right) / 2 + transform.x
    center_y = (top + bottom) / 2 + transform.y
    target_left = round(center_x - item.width / 2)
    target_top = round(center_y - item.height / 2)
    positioned = Image.new("RGBA", ROOM_CANVAS_SIZE, (0, 0, 0, 0))
    positioned.alpha_composite(item, (target_left, target_top))
    return positioned


@lru_cache(maxsize=16)
def _build_fixed_room_data_url(
    background_item_key: str | None,
    floor_item_key: str | None,
) -> str:
    """고정 배경·바닥을 합성한 편집기용 WebP data URL을 캐시합니다."""

    with Image.open(BASE_ROOM_PATH) as base_source:
        room = base_source.convert("RGBA")
    for item_key in (background_item_key, floor_item_key):
        if item_key is None:
            continue
        overlay_path = PROJECT_ROOT / SHOP_ITEMS_BY_KEY[item_key].overlay_path
        with Image.open(overlay_path) as overlay_source:
            overlay = overlay_source.convert("RGBA")
        room.alpha_composite(overlay)
    output = BytesIO()
    room.convert("RGB").save(output, format="WEBP", quality=90, method=6)
    return _data_url(output.getvalue(), "image/webp")


@lru_cache(maxsize=32)
def _cropped_overlay_data(
    item_key: str,
) -> tuple[str, tuple[int, int, int, int]]:
    """투명 여백을 제거한 아이템 PNG와 원래 배치 경계를 캐시합니다."""

    item = SHOP_ITEMS_BY_KEY[item_key]
    overlay_path = PROJECT_ROOT / item.overlay_path
    with Image.open(overlay_path) as overlay_source:
        overlay = overlay_source.convert("RGBA")
    bounds = overlay.getchannel("A").getbbox()
    if bounds is None:
        raise RuntimeError("학습방 아이템 이미지에서 유효한 영역을 찾지 못했습니다.")
    cropped = overlay.crop(bounds)
    output = BytesIO()
    cropped.save(output, format="PNG", optimize=True)
    return _data_url(output.getvalue(), "image/png"), bounds


def _data_url(content: bytes, media_type: str) -> str:
    """로컬 이미지 바이트를 브라우저 컴포넌트가 읽을 data URL로 변환합니다."""

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
