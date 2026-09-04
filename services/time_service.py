from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
UTC_TIMEZONE = timezone.utc


def get_seoul_now() -> datetime:
    """사용자 일일 기준인 서울 현재 시각을 반환합니다."""

    return datetime.now(SEOUL_TIMEZONE)


def get_seoul_today() -> date:
    """사용자 일일 기준인 서울 현재 날짜를 반환합니다."""

    return get_seoul_now().date()
