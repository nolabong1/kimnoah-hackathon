from supabase import Client


MAX_AUTH_TOKEN_LENGTH = 20_000


def _validate_auth_token(
    token,
    token_name: str,
) -> str:
    """브라우저에서 전달된 인증 토큰의 기본 형식을 검사합니다."""

    if not isinstance(token, str):
        raise ValueError(
            f"{token_name} 형식이 올바르지 않습니다."
        )

    cleaned_token = token.strip()

    if (
        not cleaned_token
        or len(cleaned_token) > MAX_AUTH_TOKEN_LENGTH
    ):
        raise ValueError(
            f"{token_name} 형식이 올바르지 않습니다."
        )

    return cleaned_token


def get_session_tokens(session) -> dict:
    """Supabase 세션에서 브라우저 저장용 토큰만 추출합니다."""

    if session is None:
        raise RuntimeError("인증 세션이 없습니다.")

    access_token = _validate_auth_token(
        session.access_token,
        "Access token",
    )
    refresh_token = _validate_auth_token(
        session.refresh_token,
        "Refresh token",
    )

    if access_token.count(".") != 2:
        raise ValueError(
            "Access token 형식이 올바르지 않습니다."
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def restore_session(
    client: Client,
    access_token,
    refresh_token,
):
    """브라우저 탭에 저장된 토큰으로 Supabase 세션을 복원합니다."""

    validated_access_token = _validate_auth_token(
        access_token,
        "Access token",
    )
    validated_refresh_token = _validate_auth_token(
        refresh_token,
        "Refresh token",
    )

    if validated_access_token.count(".") != 2:
        raise ValueError(
            "Access token 형식이 올바르지 않습니다."
        )

    response = client.auth.set_session(
        validated_access_token,
        validated_refresh_token,
    )

    if response.session is None or response.user is None:
        raise RuntimeError("인증 세션을 복원하지 못했습니다.")

    return response


def sign_up(
    client: Client,
    nickname: str,
    email: str,
    password: str,
):
    """이메일 계정을 만들고 닉네임을 사용자 메타데이터로 전달합니다."""

    return client.auth.sign_up(
        {
            "email": email.strip(),
            "password": password,
            "options": {
                "data": {
                    "nickname": nickname.strip(),
                }
            },
        }
    )


def sign_in(client: Client, email: str, password: str):
    """이메일과 비밀번호로 로그인합니다."""

    return client.auth.sign_in_with_password(
        {
            "email": email.strip(),
            "password": password,
        }
    )


def sign_out(client: Client) -> None:
    """현재 사용자를 로그아웃합니다."""

    client.auth.sign_out()
