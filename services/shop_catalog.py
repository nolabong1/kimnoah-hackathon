from models.shop import (
    ShopItem,
    ShopItemCategory,
    ShopItemRarity,
    StudyRoomSlot,
)


def _item(
    item_key: str,
    name_ko: str,
    category: ShopItemCategory,
    slots: tuple[StudyRoomSlot, ...],
    rarity: ShopItemRarity,
    price: int,
    layer: int,
    asset_folder: str,
    sort_order: int,
) -> ShopItem:
    """승인된 파일 규칙을 적용해 상점 아이템 정의를 만듭니다."""

    return ShopItem(
        item_key=item_key,
        name_ko=name_ko,
        category=category,
        allowed_slots=slots,
        rarity=rarity,
        price=price,
        layer=layer,
        overlay_path=(
            f"assets/study_room/items/{asset_folder}/{item_key}.png"
        ),
        thumbnail_path=(
            f"assets/study_room/thumbnails/{item_key}.webp"
        ),
        sort_order=sort_order,
    )


SHOP_ITEM_CATALOG: tuple[ShopItem, ...] = (
    _item(
        "wall_morning_sky", "아침 하늘 벽지",
        ShopItemCategory.BACKGROUND, (StudyRoomSlot.BACKGROUND,),
        ShopItemRarity.COMMON, 40, 0, "backgrounds", 10,
    ),
    _item(
        "wall_warm_cream", "따뜻한 크림 벽지",
        ShopItemCategory.BACKGROUND, (StudyRoomSlot.BACKGROUND,),
        ShopItemRarity.COMMON, 40, 0, "backgrounds", 20,
    ),
    _item(
        "wall_night_focus", "밤의 집중 벽지",
        ShopItemCategory.BACKGROUND, (StudyRoomSlot.BACKGROUND,),
        ShopItemRarity.RARE, 160, 0, "backgrounds", 30,
    ),
    _item(
        "floor_light_wood", "밝은 원목 바닥",
        ShopItemCategory.FLOOR, (StudyRoomSlot.FLOOR,),
        ShopItemRarity.COMMON, 35, 10, "floors", 40,
    ),
    _item(
        "floor_soft_gray", "부드러운 회색 바닥",
        ShopItemCategory.FLOOR, (StudyRoomSlot.FLOOR,),
        ShopItemRarity.COMMON, 35, 10, "floors", 50,
    ),
    _item(
        "floor_starry_rug", "별빛 러그 바닥",
        ShopItemCategory.FLOOR, (StudyRoomSlot.FLOOR,),
        ShopItemRarity.UNCOMMON, 80, 10, "floors", 60,
    ),
    _item(
        "desk_oak_basic", "원목 학습 책상",
        ShopItemCategory.DESK, (StudyRoomSlot.DESK,),
        ShopItemRarity.COMMON, 60, 30, "desks", 70,
    ),
    _item(
        "desk_white_clean", "화이트 학습 책상",
        ShopItemCategory.DESK, (StudyRoomSlot.DESK,),
        ShopItemRarity.UNCOMMON, 85, 30, "desks", 80,
    ),
    _item(
        "desk_neon_coder", "네온 코딩 책상",
        ShopItemCategory.DESK, (StudyRoomSlot.DESK,),
        ShopItemRarity.RARE, 170, 30, "desks", 90,
    ),
    _item(
        "chair_blue_basic", "블루 학습 의자",
        ShopItemCategory.CHAIR, (StudyRoomSlot.CHAIR,),
        ShopItemRarity.COMMON, 50, 40, "chairs", 100,
    ),
    _item(
        "chair_ergonomic", "집중 인체공학 의자",
        ShopItemCategory.CHAIR, (StudyRoomSlot.CHAIR,),
        ShopItemRarity.UNCOMMON, 100, 40, "chairs", 110,
    ),
    _item(
        "decor_green_plant", "작은 초록 식물",
        ShopItemCategory.DECORATION,
        (StudyRoomSlot.DECOR_LEFT, StudyRoomSlot.DECOR_RIGHT),
        ShopItemRarity.COMMON, 30, 50, "decorations", 120,
    ),
    _item(
        "decor_focus_lamp", "집중 스탠드",
        ShopItemCategory.DECORATION,
        (StudyRoomSlot.DECOR_LEFT, StudyRoomSlot.DECOR_RIGHT),
        ShopItemRarity.COMMON, 45, 50, "decorations", 130,
    ),
    _item(
        "decor_bookshelf", "미니 학습 책장",
        ShopItemCategory.DECORATION,
        (StudyRoomSlot.DECOR_LEFT, StudyRoomSlot.DECOR_RIGHT),
        ShopItemRarity.UNCOMMON, 90, 50, "decorations", 140,
    ),
    _item(
        "accent_study_cat", "공부하는 고양이",
        ShopItemCategory.ACCENT, (StudyRoomSlot.ACCENT,),
        ShopItemRarity.RARE, 150, 60, "accents", 150,
    ),
)


SHOP_ITEMS_BY_KEY = {item.item_key: item for item in SHOP_ITEM_CATALOG}
