from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


STUDY_ROOM_CANVAS_WIDTH: Final[int] = 1600
STUDY_ROOM_CANVAS_HEIGHT: Final[int] = 900
STUDY_ROOM_TRANSFORM_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "x": (-800, 800),
    "y": (-450, 450),
    "scale": (25, 200),
    "rotation": (-180, 180),
}


class ShopItemCategory(StrEnum):
    """꾸미기 아이템을 분류하는 고정 카테고리입니다."""

    BACKGROUND = "background"
    FLOOR = "floor"
    DESK = "desk"
    CHAIR = "chair"
    DECORATION = "decoration"
    ACCENT = "accent"


class StudyRoomSlot(StrEnum):
    """학습방에서 아이템을 장착할 수 있는 고정 슬롯입니다."""

    BACKGROUND = "background"
    FLOOR = "floor"
    DESK = "desk"
    CHAIR = "chair"
    DECOR_LEFT = "decor_left"
    DECOR_RIGHT = "decor_right"
    ACCENT = "accent"


class ShopItemRarity(StrEnum):
    """상점 아이템의 가격대와 수집 등급입니다."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"


CATEGORY_SLOTS = {
    ShopItemCategory.BACKGROUND: (StudyRoomSlot.BACKGROUND,),
    ShopItemCategory.FLOOR: (StudyRoomSlot.FLOOR,),
    ShopItemCategory.DESK: (StudyRoomSlot.DESK,),
    ShopItemCategory.CHAIR: (StudyRoomSlot.CHAIR,),
    ShopItemCategory.DECORATION: (
        StudyRoomSlot.DECOR_LEFT,
        StudyRoomSlot.DECOR_RIGHT,
    ),
    ShopItemCategory.ACCENT: (StudyRoomSlot.ACCENT,),
}

CATEGORY_LAYERS = {
    ShopItemCategory.BACKGROUND: 0,
    ShopItemCategory.FLOOR: 10,
    ShopItemCategory.DESK: 30,
    ShopItemCategory.CHAIR: 40,
    ShopItemCategory.DECORATION: 50,
    ShopItemCategory.ACCENT: 60,
}


class ShopItem(BaseModel, frozen=True):
    """서버가 가격과 장착 규칙을 결정하는 상점 카탈로그 항목입니다."""

    item_key: str = Field(
        pattern=r"^[a-z0-9_]+$",
        min_length=1,
        max_length=100,
    )
    name_ko: str = Field(min_length=1, max_length=100)
    category: ShopItemCategory
    allowed_slots: tuple[StudyRoomSlot, ...] = Field(
        min_length=1,
        max_length=2,
    )
    rarity: ShopItemRarity
    price: int = Field(gt=0)
    layer: int = Field(ge=0, le=100)
    overlay_path: str = Field(min_length=1, max_length=300)
    thumbnail_path: str = Field(min_length=1, max_length=300)
    sort_order: int = Field(gt=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_slot_and_layer(self) -> "ShopItem":
        """카테고리별 슬롯과 합성 레이어가 고정 규칙과 같은지 검사합니다."""

        if self.allowed_slots != CATEGORY_SLOTS[self.category]:
            raise ValueError("상점 아이템의 장착 슬롯이 카테고리와 다릅니다.")
        if self.layer != CATEGORY_LAYERS[self.category]:
            raise ValueError("상점 아이템의 합성 레이어가 카테고리와 다릅니다.")
        return self


class UserInventoryItem(BaseModel):
    """사용자가 구매하여 영구 소유하는 꾸미기 아이템입니다."""

    user_id: UUID
    item_key: str = Field(
        pattern=r"^[a-z0-9_]+$",
        min_length=1,
        max_length=100,
    )
    purchase_transaction_id: UUID
    price_paid: int = Field(gt=0)
    acquired_at: datetime


class StudyRoomEquipment(BaseModel):
    """학습방의 일곱 고정 슬롯에 장착한 아이템 키입니다."""

    background_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    floor_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    desk_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    chair_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    decor_left_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    decor_right_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )
    accent_item_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_decorations_are_distinct(self) -> "StudyRoomEquipment":
        """같은 소품을 좌우 슬롯에 동시에 장착하지 못하게 합니다."""

        if (
            self.decor_left_item_key is not None
            and self.decor_left_item_key == self.decor_right_item_key
        ):
            raise ValueError("같은 소품을 좌우 슬롯에 동시에 장착할 수 없습니다.")
        return self


class StudyRoomItemTransform(BaseModel):
    """고정 배치점을 기준으로 적용하는 개별 에셋의 2D 변형값입니다."""

    x: int = Field(
        default=0,
        ge=STUDY_ROOM_TRANSFORM_LIMITS["x"][0],
        le=STUDY_ROOM_TRANSFORM_LIMITS["x"][1],
    )
    y: int = Field(
        default=0,
        ge=STUDY_ROOM_TRANSFORM_LIMITS["y"][0],
        le=STUDY_ROOM_TRANSFORM_LIMITS["y"][1],
    )
    scale: int = Field(
        default=100,
        ge=STUDY_ROOM_TRANSFORM_LIMITS["scale"][0],
        le=STUDY_ROOM_TRANSFORM_LIMITS["scale"][1],
    )
    rotation: int = Field(
        default=0,
        ge=STUDY_ROOM_TRANSFORM_LIMITS["rotation"][0],
        le=STUDY_ROOM_TRANSFORM_LIMITS["rotation"][1],
    )
    flip_horizontal: bool = False


class StudyRoomTransforms(BaseModel):
    """배경과 바닥을 제외한 다섯 학습방 슬롯의 사용자 배치값입니다."""

    desk: StudyRoomItemTransform = Field(
        default_factory=StudyRoomItemTransform
    )
    chair: StudyRoomItemTransform = Field(
        default_factory=StudyRoomItemTransform
    )
    decor_left: StudyRoomItemTransform = Field(
        default_factory=StudyRoomItemTransform
    )
    decor_right: StudyRoomItemTransform = Field(
        default_factory=StudyRoomItemTransform
    )
    accent: StudyRoomItemTransform = Field(
        default_factory=StudyRoomItemTransform
    )


class StudyRoomLayout(StudyRoomEquipment):
    """장착 아이템과 직접 편집한 2D 배치를 함께 표현합니다."""

    item_transforms: StudyRoomTransforms = Field(
        default_factory=StudyRoomTransforms
    )


class UserStudyRoom(StudyRoomLayout):
    """사용자별로 서버에 저장된 현재 학습방 구성입니다."""

    user_id: UUID
    created_at: datetime
    updated_at: datetime


class ShopPurchaseResult(BaseModel):
    """원자적 상점 구매 RPC의 검증된 결과입니다."""

    item_key: str = Field(
        pattern=r"^[a-z0-9_]+$",
        min_length=1,
        max_length=100,
    )
    price: int = Field(gt=0)
    coins_spent: int = Field(ge=0)
    balance: int = Field(ge=0)
    already_owned: bool
    purchase_transaction_id: UUID
    acquired_at: datetime

    @model_validator(mode="after")
    def validate_purchase_amount(self) -> "ShopPurchaseResult":
        """새 구매와 중복 요청의 차감 금액을 구분해 검증합니다."""

        expected_spent = 0 if self.already_owned else self.price
        if self.coins_spent != expected_spent:
            raise ValueError("상점 구매 차감 금액이 가격과 일치하지 않습니다.")
        return self


class ShopTestSession(BaseModel):
    """현재 사용자에게 열려 있는 상점 테스트 세션입니다."""

    id: UUID
    user_id: UUID
    status: str = Field(pattern=r"^active$")
    credit_amount: int = Field(gt=0)
    credit_transaction_id: UUID
    inventory_snapshot: list[str]
    room_snapshot: dict | None = None
    refunded_purchase_count: int = Field(ge=0)
    refunded_coin_amount: int = Field(ge=0)
    removed_inventory_count: int = Field(ge=0)
    balance_after_reset: int | None = Field(default=None, ge=0)
    started_at: datetime
    reset_at: datetime | None = None


class ShopTestStartResult(BaseModel):
    """상점 테스트 코인 지급 RPC 결과입니다."""

    session_id: UUID
    credit_amount: int = Field(gt=0)
    balance: int = Field(ge=0)
    already_active: bool
    started_at: datetime


class ShopTestResetResult(BaseModel):
    """상점 테스트 구매·학습방 복원 RPC 결과입니다."""

    session_id: UUID
    refunded_purchase_count: int = Field(ge=0)
    refunded_coin_amount: int = Field(ge=0)
    removed_inventory_count: int = Field(ge=0)
    balance: int = Field(ge=0)
    already_reset: bool
    reset_at: datetime

    @model_validator(mode="after")
    def validate_reset_counts(self) -> "ShopTestResetResult":
        """제거한 테스트 아이템 수와 환급한 구매 수를 맞춥니다."""

        if self.removed_inventory_count != self.refunded_purchase_count:
            raise ValueError("상점 테스트 구매와 제거 수가 일치하지 않습니다.")
        if self.refunded_purchase_count == 0 and self.refunded_coin_amount != 0:
            raise ValueError("구매가 없는데 환급 코인이 기록됐습니다.")
        return self
