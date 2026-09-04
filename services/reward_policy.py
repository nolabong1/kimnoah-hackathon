from typing import Final


TASK_COMPLETION_EXP: Final[int] = 10
DAILY_COMPLETION_BONUS_EXP: Final[int] = 20
EXP_PER_LEVEL: Final[int] = 100


def calculate_level(total_exp: int) -> int:
    """서버 보상 규칙과 같은 방식으로 누적 EXP의 레벨을 계산합니다."""

    if isinstance(total_exp, bool) or not isinstance(total_exp, int):
        raise ValueError("총 EXP는 정수여야 합니다.")
    if total_exp < 0:
        raise ValueError("총 EXP는 0 이상이어야 합니다.")
    return (total_exp // EXP_PER_LEVEL) + 1
