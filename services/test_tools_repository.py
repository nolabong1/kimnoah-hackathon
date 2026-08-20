from supabase import Client


def can_use_test_tools(supabase: Client) -> bool:
    """현재 인증 사용자의 개발용 테스트 도구 권한을 서버에서 확인합니다."""

    response = supabase.rpc("can_use_test_tools", {}).execute()
    if not isinstance(response.data, bool):
        raise RuntimeError("테스트 도구 권한 확인 결과가 올바르지 않습니다.")
    return response.data
