from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.dashboard import DashboardSnapshot


def get_dashboard_snapshot(
    supabase: Client,
    user_id: str,
    plan_id: str,
    course_key: str,
) -> dict:
    """본인 선택 계획의 대시보드 표시 데이터를 단일 RPC로 조회합니다."""

    normalized_user_id = _validate_uuid(user_id, "사용자 ID")
    normalized_plan_id = _validate_uuid(plan_id, "학습계획 ID")
    normalized_course_key = _validate_course_key(course_key)

    response = (
        supabase.rpc(
            "get_dashboard_snapshot",
            {
                "p_plan_id": normalized_plan_id,
                "p_course_key": normalized_course_key,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError("오늘 학습 요약 조회 결과가 비어 있습니다.")

    try:
        snapshot = DashboardSnapshot.model_validate(response.data)
    except ValidationError as error:
        raise RuntimeError(
            "오늘 학습 요약 조회 결과가 올바르지 않습니다."
        ) from error

    if str(snapshot.user_id) != normalized_user_id:
        raise RuntimeError("오늘 학습 요약의 사용자 소유권이 일치하지 않습니다.")
    if str(snapshot.plan_id) != normalized_plan_id:
        raise RuntimeError("오늘 학습 요약의 학습계획이 일치하지 않습니다.")

    return snapshot.model_dump(mode="json")


def _validate_uuid(value: str, field_name: str) -> str:
    """대시보드 RPC에 전달할 UUID 문자열을 정규화합니다."""

    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def _validate_course_key(value: str) -> str:
    """정규화된 과목 키의 데이터베이스 길이 규칙을 확인합니다."""

    if not isinstance(value, str):
        raise ValueError("과목 키 형식이 올바르지 않습니다.")
    normalized_value = value.strip()
    if not 1 <= len(normalized_value) <= 120:
        raise ValueError("과목 키는 1자 이상 120자 이하여야 합니다.")
    return normalized_value
