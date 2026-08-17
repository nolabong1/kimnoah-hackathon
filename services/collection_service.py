from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from models.shop import ShopItemCategory
from services.study_room_service import extract_study_room_equipment


@dataclass(frozen=True)
class CategoryCollectionProgress:
    """카테고리 하나의 수집 진행도를 나타냅니다."""

    category: str
    total_count: int
    owned_count: int
    completion_percent: int


@dataclass(frozen=True)
class CollectionSummary:
    """전체 꾸미기 아이템 수집 현황의 읽기 전용 요약입니다."""

    total_count: int
    owned_count: int
    equipped_count: int
    completion_percent: int
    owned_keys: frozenset[str]
    equipped_keys: frozenset[str]
    category_progress: tuple[CategoryCollectionProgress, ...]


def build_collection_summary(
    items: Sequence[Mapping[str, object]],
    inventory: Sequence[Mapping[str, object]],
    saved_room: Mapping[str, object] | None,
) -> CollectionSummary:
    """활성 카탈로그·보유 목록·저장된 방으로 수집 현황을 계산합니다."""

    active_items = {
        str(item["item_key"]): item
        for item in items
        if item.get("is_active", True) and item.get("item_key")
    }
    catalog_keys = set(active_items)
    inventory_keys = {
        str(entry["item_key"])
        for entry in inventory
        if entry.get("item_key")
    }
    owned_keys = frozenset(catalog_keys & inventory_keys)

    equipment = extract_study_room_equipment(saved_room)
    equipped_keys = frozenset(
        item_key
        for item_key in equipment.values()
        if item_key in owned_keys
    )

    category_progress = tuple(
        _category_progress(
            category.value,
            active_items,
            owned_keys,
        )
        for category in ShopItemCategory
    )
    total_count = len(catalog_keys)
    owned_count = len(owned_keys)
    return CollectionSummary(
        total_count=total_count,
        owned_count=owned_count,
        equipped_count=len(equipped_keys),
        completion_percent=_percentage(owned_count, total_count),
        owned_keys=owned_keys,
        equipped_keys=equipped_keys,
        category_progress=category_progress,
    )


def _category_progress(
    category: str,
    active_items: Mapping[str, Mapping[str, object]],
    owned_keys: frozenset[str],
) -> CategoryCollectionProgress:
    """카테고리별 전체·보유 수를 중복 없이 계산합니다."""

    category_keys = {
        item_key
        for item_key, item in active_items.items()
        if item.get("category") == category
    }
    owned_count = len(category_keys & owned_keys)
    total_count = len(category_keys)
    return CategoryCollectionProgress(
        category=category,
        total_count=total_count,
        owned_count=owned_count,
        completion_percent=_percentage(owned_count, total_count),
    )


def _percentage(value: int, total: int) -> int:
    """0건을 안전하게 처리하며 정수 백분율을 반환합니다."""

    if total <= 0:
        return 0
    return round(value / total * 100)
