from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.gamification import (
    BadgeShowcaseSlot,
    ChallengeClaimResult,
    GamificationSyncResult,
    UserAchievementState,
    UserChallengeState,
)
from services.gamification_catalog import ACHIEVEMENTS_BY_KEY


def sync_gamification_state(supabase: Client) -> dict:
    """현재 인증 사용자의 업적과 도전과제를 서버에서 동기화합니다."""

    response = supabase.rpc("sync_gamification_state", {}).execute()
    return validate_gamification_sync_result(response.data)


def validate_gamification_sync_result(data) -> dict:
    """학습 행동 래퍼에 포함된 게임화 결과를 동일하게 검증합니다."""

    return _validate_single_response(
        data,
        GamificationSyncResult,
        "게임화 동기화 결과가 올바르지 않습니다.",
    )


def get_user_achievements(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자 본인의 업적 진행 상태를 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_achievements")
        .select(
            "id, user_id, achievement_key, progress_value, "
            "unlocked_at, rewarded_at, progress_snapshot, "
            "created_at, updated_at"
        )
        .eq("user_id", normalized_user_id)
        .order("created_at")
        .execute()
    )
    return _validate_list_response(
        response.data,
        UserAchievementState,
        "업적 조회 결과가 올바르지 않습니다.",
    )


def get_user_challenges(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자 본인의 저장된 도전과제를 최근 기간순으로 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_challenges")
        .select(
            "id, user_id, template_key, period_type, period_start, "
            "period_end, display_order, target_value, progress_value, "
            "reward_exp, status, completed_at, claimed_at, "
            "eligibility_snapshot, created_at, updated_at"
        )
        .eq("user_id", normalized_user_id)
        .order("period_start", desc=True)
        .order("display_order")
        .execute()
    )
    return _validate_list_response(
        response.data,
        UserChallengeState,
        "도전과제 조회 결과가 올바르지 않습니다.",
    )


def claim_challenge_reward(
    supabase: Client,
    challenge_id: str,
) -> dict:
    """완료한 도전과제의 서버 고정 EXP를 한 번만 수령합니다."""

    normalized_challenge_id = _validate_uuid(
        challenge_id,
        "도전과제 ID",
    )
    response = (
        supabase.rpc(
            "claim_gamification_challenge",
            {"p_challenge_id": normalized_challenge_id},
        )
        .execute()
    )
    return _validate_single_response(
        response.data,
        ChallengeClaimResult,
        "도전과제 보상 수령 결과가 올바르지 않습니다.",
    )


def get_badge_showcase(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자 본인의 대표 배지 슬롯을 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    response = (
        supabase.table("user_badge_showcase")
        .select("user_id, slot, achievement_key, equipped_at")
        .eq("user_id", normalized_user_id)
        .order("slot")
        .execute()
    )
    return _validate_list_response(
        response.data,
        BadgeShowcaseSlot,
        "대표 배지 조회 결과가 올바르지 않습니다.",
    )


def equip_badge(
    supabase: Client,
    achievement_key: str,
    slot: int,
) -> dict:
    """해금한 업적 배지를 대표 슬롯 하나에 장착합니다."""

    normalized_key = _validate_achievement_key(achievement_key)
    normalized_slot = _validate_badge_slot(slot)
    response = (
        supabase.rpc(
            "equip_gamification_badge",
            {
                "p_achievement_key": normalized_key,
                "p_slot": normalized_slot,
            },
        )
        .execute()
    )
    return _validate_single_response(
        response.data,
        BadgeShowcaseSlot,
        "대표 배지 장착 결과가 올바르지 않습니다.",
    )


def remove_badge(supabase: Client, slot: int) -> dict:
    """대표 배지 슬롯 하나를 비웁니다."""

    normalized_slot = _validate_badge_slot(slot)
    response = (
        supabase.rpc(
            "remove_gamification_badge",
            {"p_slot": normalized_slot},
        )
        .execute()
    )
    data = response.data
    if not isinstance(data, dict):
        raise RuntimeError("대표 배지 해제 결과가 올바르지 않습니다.")
    if data.get("slot") != normalized_slot:
        raise RuntimeError("대표 배지 해제 슬롯이 일치하지 않습니다.")
    if not isinstance(data.get("removed"), bool):
        raise RuntimeError("대표 배지 해제 상태가 올바르지 않습니다.")
    return data


def _validate_uuid(value: str, field_name: str) -> str:
    """RPC와 소유권 조회에 사용할 UUID 문자열을 정규화합니다."""

    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def _validate_achievement_key(value: str) -> str:
    """서버 카탈로그에 있는 업적 키만 장착 요청에 허용합니다."""

    if not isinstance(value, str):
        raise ValueError("업적 키 형식이 올바르지 않습니다.")
    normalized_value = value.strip()
    if normalized_value not in ACHIEVEMENTS_BY_KEY:
        raise ValueError("지원하지 않는 업적 배지입니다.")
    return normalized_value


def _validate_badge_slot(value: int) -> int:
    """대표 배지는 1번부터 3번 슬롯에만 장착합니다."""

    if isinstance(value, bool) or not isinstance(value, int) or value not in range(1, 4):
        raise ValueError("대표 배지 슬롯은 1부터 3 사이여야 합니다.")
    return value


def _validate_single_response(data, model_type, error_message: str) -> dict:
    """단일 RPC 응답을 지정한 Pydantic 모델로 검증합니다."""

    if not isinstance(data, dict):
        raise RuntimeError(error_message)
    try:
        return model_type.model_validate(data).model_dump(mode="json")
    except ValidationError as error:
        raise RuntimeError(error_message) from error


def _validate_list_response(data, model_type, error_message: str) -> list[dict]:
    """목록 조회 응답의 각 행을 Pydantic 모델로 검증합니다."""

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
