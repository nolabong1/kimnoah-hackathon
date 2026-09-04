from typing import Final

from models.gamification import AchievementCategory
from models.shop import ShopItemCategory


TASK_TYPE_LABELS: Final[dict[str, str]] = {
    "learn": "학습",
    "review": "복습",
    "quiz": "퀴즈",
}

SOURCE_MATERIAL_TYPE_LABELS: Final[dict[str, str]] = {
    "text": "텍스트",
    "pdf": "PDF",
    "image": "이미지",
}

SHOP_CATEGORY_LABELS: Final[dict[str, str]] = {
    ShopItemCategory.BACKGROUND.value: "배경",
    ShopItemCategory.FLOOR.value: "바닥",
    ShopItemCategory.DESK.value: "책상",
    ShopItemCategory.CHAIR.value: "의자",
    ShopItemCategory.DECORATION.value: "장식",
    ShopItemCategory.ACCENT.value: "포인트",
}

SHOP_RARITY_LABELS: Final[dict[str, str]] = {
    "common": "일반",
    "uncommon": "고급",
    "rare": "희귀",
}

ACHIEVEMENT_CATEGORY_LABELS: Final[dict[AchievementCategory, str]] = {
    AchievementCategory.TASK: "과제",
    AchievementCategory.STREAK: "연속 학습",
    AchievementCategory.PLAN: "계획",
    AchievementCategory.REVIEW: "복습",
    AchievementCategory.QUIZ: "퀴즈",
    AchievementCategory.BALANCE: "균형",
}

ACHIEVEMENT_TIER_LABELS: Final[dict[str, str]] = {
    "bronze": "브론즈",
    "silver": "실버",
    "gold": "골드",
    "platinum": "플래티넘",
}

BADGE_RARITY_LABELS: Final[dict[str, str]] = {
    **SHOP_RARITY_LABELS,
    "epic": "영웅",
    "legendary": "전설",
}
