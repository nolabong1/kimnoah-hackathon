from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CoinTransactionType(StrEnum):
    """코인 원장에서 허용하는 거래 유형입니다."""

    ONBOARDING = "onboarding"
    TASK_COMPLETION = "task_completion"
    DAILY_COMPLETION = "daily_completion"
    DAILY_CHALLENGE = "daily_challenge"
    WEEKLY_CHALLENGE = "weekly_challenge"
    PURCHASE = "purchase"
    TEST_RESET_REVERSAL = "test_reset_reversal"


POSITIVE_COIN_TRANSACTION_TYPES = {
    CoinTransactionType.ONBOARDING,
    CoinTransactionType.TASK_COMPLETION,
    CoinTransactionType.DAILY_COMPLETION,
    CoinTransactionType.DAILY_CHALLENGE,
    CoinTransactionType.WEEKLY_CHALLENGE,
}


class CoinWallet(BaseModel):
    """사용자별 현재 코인 잔액과 누적 합계입니다."""

    user_id: UUID
    balance: int = Field(ge=0)
    lifetime_earned: int = Field(ge=0)
    lifetime_spent: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_balance_totals(self) -> "CoinWallet":
        """현재 잔액이 누적 획득과 사용 차이와 일치하는지 확인합니다."""

        if self.balance != self.lifetime_earned - self.lifetime_spent:
            raise ValueError("코인 지갑 잔액과 누적 합계가 일치하지 않습니다.")
        return self

class CoinTransaction(BaseModel):
    """서버가 기록한 멱등 코인 증감 원장 한 건입니다."""

    id: UUID
    user_id: UUID
    transaction_type: CoinTransactionType
    amount: int
    balance_after: int = Field(ge=0)
    source_key: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9:_-]+$",
    )
    related_entity_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime

    @model_validator(mode="after")
    def validate_amount_direction(self) -> "CoinTransaction":
        """지급과 사용 거래가 올바른 금액 방향인지 확인합니다."""

        if self.amount == 0:
            raise ValueError("코인 거래 금액은 0일 수 없습니다.")

        expects_positive = (
            self.transaction_type in POSITIVE_COIN_TRANSACTION_TYPES
        )
        if expects_positive and self.amount < 0:
            raise ValueError("코인 지급 거래 금액은 양수여야 합니다.")
        if not expects_positive and self.amount > 0:
            raise ValueError("코인 사용 또는 취소 거래 금액은 음수여야 합니다.")
        return self
