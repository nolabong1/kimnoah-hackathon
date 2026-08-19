from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.coin_economy import CoinWallet
from models.shop import (
    ShopItem,
    ShopPurchaseResult,
    ShopTestResetResult,
    ShopTestSession,
    ShopTestStartResult,
    StudyRoomEquipment,
    StudyRoomTransforms,
    UserInventoryItem,
    UserStudyRoom,
)
from services.shop_catalog import SHOP_ITEMS_BY_KEY


def get_shop_items(supabase: Client) -> list[dict]:
    """현재 구매 가능한 서버 상점 카탈로그를 조회합니다."""

    response = (
        supabase.table("shop_items")
        .select(
            "item_key, name_ko, category, allowed_slots, rarity, price, "
            "layer, overlay_path, thumbnail_path, sort_order, is_active"
        )
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return _validate_list_response(
        response.data,
        ShopItem,
        "상점 카탈로그 조회 결과가 올바르지 않습니다.",
    )


def get_user_coin_wallet(
    supabase: Client,
    user_id: str,
) -> dict:
    """사용자 본인의 현재 코인 지갑을 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_coin_wallets")
        .select(
            "user_id, balance, lifetime_earned, lifetime_spent, "
            "created_at, updated_at"
        )
        .eq("user_id", normalized_user_id)
        .maybe_single()
        .execute()
    )
    return _validate_single_response(
        response.data,
        CoinWallet,
        "코인 지갑 조회 결과가 올바르지 않습니다.",
    )


def get_user_inventory(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자 본인이 영구 소유한 상점 아이템을 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_inventory")
        .select(
            "user_id, item_key, purchase_transaction_id, price_paid, "
            "acquired_at"
        )
        .eq("user_id", normalized_user_id)
        .order("acquired_at")
        .execute()
    )
    return _validate_list_response(
        response.data,
        UserInventoryItem,
        "보유 아이템 조회 결과가 올바르지 않습니다.",
    )


def get_user_study_room(
    supabase: Client,
    user_id: str,
) -> dict | None:
    """사용자 본인의 저장된 학습방 한 건을 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_study_rooms")
        .select(
            "user_id, background_item_key, floor_item_key, "
            "desk_item_key, chair_item_key, decor_left_item_key, "
            "decor_right_item_key, accent_item_key, item_transforms, "
            "created_at, updated_at"
        )
        .eq("user_id", normalized_user_id)
        .maybe_single()
        .execute()
    )
    if response is None or response.data is None:
        return None
    return _validate_single_response(
        response.data,
        UserStudyRoom,
        "학습방 조회 결과가 올바르지 않습니다.",
    )


def get_active_shop_test_session(
    supabase: Client,
    user_id: str,
) -> dict | None:
    """사용자 본인의 활성 상점 테스트 세션을 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("shop_test_sessions")
        .select(
            "id, user_id, status, credit_amount, credit_transaction_id, "
            "inventory_snapshot, room_snapshot, refunded_purchase_count, "
            "refunded_coin_amount, removed_inventory_count, "
            "balance_after_reset, started_at, reset_at"
        )
        .eq("user_id", normalized_user_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    if response is None or response.data is None:
        return None
    return _validate_single_response(
        response.data,
        ShopTestSession,
        "상점 테스트 세션 조회 결과가 올바르지 않습니다.",
    )


def save_user_study_room(
    supabase: Client,
    equipment: dict,
    transforms: dict | None = None,
) -> dict:
    """서버 RPC로 보유·슬롯 검증을 거쳐 학습방을 저장합니다."""

    try:
        normalized = StudyRoomEquipment.model_validate(equipment)
    except ValidationError as error:
        raise ValueError("학습방 장착 정보가 올바르지 않습니다.") from error
    try:
        normalized_transforms = StudyRoomTransforms.model_validate(
            transforms or {}
        )
    except ValidationError as error:
        raise ValueError("학습방 가구 배치 정보가 올바르지 않습니다.") from error

    params = {
        f"p_{field_name}": value
        for field_name, value in normalized.model_dump().items()
    }
    params["p_item_transforms"] = normalized_transforms.model_dump(
        mode="json"
    )
    response = (
        supabase.rpc(
            "save_user_study_room",
            params,
        )
        .execute()
    )
    return _validate_single_response(
        response.data,
        UserStudyRoom,
        "학습방 저장 결과가 올바르지 않습니다.",
    )


def purchase_shop_item(
    supabase: Client,
    item_key: str,
) -> dict:
    """서버 고정 가격으로 아이템 하나를 원자적으로 구매합니다."""

    normalized_item_key = _validate_item_key(item_key)
    response = (
        supabase.rpc(
            "purchase_shop_item",
            {"p_item_key": normalized_item_key},
        )
        .execute()
    )
    return _validate_single_response(
        response.data,
        ShopPurchaseResult,
        "상점 구매 결과가 올바르지 않습니다.",
    )


def start_shop_test_session(supabase: Client) -> dict:
    """기존 상태를 보존하고 상점 테스트 코인을 한 번 지급합니다."""

    response = supabase.rpc("start_shop_test_session", {}).execute()
    return _validate_single_response(
        response.data,
        ShopTestStartResult,
        "상점 테스트 시작 결과가 올바르지 않습니다.",
    )


def reset_shop_test_session(
    supabase: Client,
    session_id: str,
) -> dict:
    """테스트 구매만 제거하고 시작 전 학습방과 코인을 복원합니다."""

    normalized_session_id = _validate_uuid(session_id, "테스트 세션 ID")
    response = (
        supabase.rpc(
            "reset_shop_test_session",
            {"p_session_id": normalized_session_id},
        )
        .execute()
    )
    return _validate_single_response(
        response.data,
        ShopTestResetResult,
        "상점 테스트 초기화 결과가 올바르지 않습니다.",
    )


def _validate_item_key(value: str) -> str:
    """현재 승인된 Python 카탈로그에 있는 아이템 키만 허용합니다."""

    if not isinstance(value, str):
        raise ValueError("상점 아이템 키 형식이 올바르지 않습니다.")
    normalized_value = value.strip()
    if normalized_value not in SHOP_ITEMS_BY_KEY:
        raise ValueError("지원하지 않는 상점 아이템입니다.")
    return normalized_value


def _validate_uuid(value: str, field_name: str) -> str:
    """소유권 조회에 사용할 UUID 문자열을 정규화합니다."""

    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def _validate_single_response(data, model_type, error_message: str) -> dict:
    """단일 조회 또는 RPC 응답을 Pydantic 모델로 검증합니다."""

    if not isinstance(data, dict):
        raise RuntimeError(error_message)
    try:
        return model_type.model_validate(data).model_dump(mode="json")
    except ValidationError as error:
        raise RuntimeError(error_message) from error


def _validate_list_response(data, model_type, error_message: str) -> list[dict]:
    """목록 응답의 각 행을 Pydantic 모델로 검증합니다."""

    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError(error_message)
    try:
        return [
            model_type.model_validate(row).model_dump(mode="json")
            for row in data
        ]
    except ValidationError as error:
        raise RuntimeError(error_message) from error
