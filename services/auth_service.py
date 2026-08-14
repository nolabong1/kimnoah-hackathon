from supabase import Client


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