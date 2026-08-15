from time import sleep

from supabase import Client


PROFILE_RETRY_DELAY_SECONDS = 1.0


def _fetch_profile(client: Client, user_id: str) -> dict:
    """사용자의 프로필을 조회합니다."""

    response = (
        client.table("profiles")
        .select("nickname, total_exp, level, current_streak")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return response.data


def _is_jwt_issued_at_future_error(error: Exception) -> bool:
    """PostgREST의 일시적인 JWT 발급 시각 오류인지 확인합니다."""

    return (
        getattr(error, "code", None) == "PGRST303"
        and getattr(error, "message", None) == "JWT issued at future"
    )


def get_profile(client: Client, user_id: str) -> dict:
    """프로필을 조회하고 JWT 시각 오류에 한해 한 번 재시도합니다."""

    try:
        return _fetch_profile(client, user_id)
    except Exception as error:
        if not _is_jwt_issued_at_future_error(error):
            raise

        sleep(PROFILE_RETRY_DELAY_SECONDS)
        return _fetch_profile(client, user_id)
