from typing import Final


STREAK_TIER_LABELS: Final[dict[str, str]] = {
    "ready": "불씨 준비",
    "spark": "첫 불씨",
    "growing": "자라는 불꽃",
    "strong": "단단한 리듬",
    "blazing": "14일 열기",
    "legendary": "30일 불꽃",
}


def resolve_streak_tier(current_streak: int) -> str:
    """연속 학습일을 화면 연출용 단계로 결정론적으로 변환합니다."""

    if (
        isinstance(current_streak, bool)
        or not isinstance(current_streak, int)
        or current_streak < 0
    ):
        raise ValueError("연속 학습일 정보가 올바르지 않습니다.")
    if current_streak >= 30:
        return "legendary"
    if current_streak >= 14:
        return "blazing"
    if current_streak >= 7:
        return "strong"
    if current_streak >= 3:
        return "growing"
    if current_streak >= 1:
        return "spark"
    return "ready"


def get_streak_tier_label(tier: str) -> str:
    """검증된 연속 학습 단계의 짧은 화면 라벨을 반환합니다."""

    try:
        return STREAK_TIER_LABELS[tier]
    except KeyError as error:
        raise ValueError("연속 학습 화면 단계가 올바르지 않습니다.") from error
