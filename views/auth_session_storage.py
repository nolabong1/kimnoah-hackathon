from uuid import uuid4

import streamlit as st

from services.auth_service import (
    get_session_tokens,
    restore_session,
)
from services.error_reporting import report_exception


AUTH_STORAGE_COMMAND_KEY = "auth_storage_command"
AUTH_STORAGE_SYNCED_TOKEN_KEY = (
    "auth_storage_synced_refresh_token"
)
AUTH_RESTORE_NOTICE_KEY = "auth_restore_notice"


AUTH_SESSION_STORAGE_HTML = """
<span hidden aria-hidden="true"></span>
"""


AUTH_SESSION_STORAGE_JS = """
const SESSION_KEY = "ai-learning-coach:supabase-session"
const handledCommandIds = new Set()

function normalizeSession(value) {
  if (!value || typeof value !== "object") return null

  const accessToken = value.access_token
  const refreshToken = value.refresh_token

  if (
    typeof accessToken !== "string" ||
    accessToken.length === 0 ||
    typeof refreshToken !== "string" ||
    refreshToken.length === 0
  ) {
    return null
  }

  return {
    access_token: accessToken,
    refresh_token: refreshToken,
  }
}

export default function (component) {
  const { data, setStateValue } = component
  const commandId = data?.command_id
  const action = data?.action
  const acknowledgedCommandId = data?.acknowledged_command_id

  if (typeof commandId !== "string" || commandId.length === 0) {
    return
  }

  if (
    acknowledgedCommandId === commandId ||
    handledCommandIds.has(commandId)
  ) {
    return
  }

  handledCommandIds.add(commandId)

  let storedSession = null
  let errorCode = null

  try {
    if (action === "read") {
      const rawSession = window.sessionStorage.getItem(SESSION_KEY)

      if (rawSession !== null) {
        storedSession = normalizeSession(JSON.parse(rawSession))

        if (storedSession === null) {
          window.sessionStorage.removeItem(SESSION_KEY)
        }
      }
    } else if (action === "write") {
      storedSession = normalizeSession(data?.session)

      if (storedSession === null) {
        throw new Error("invalid_session")
      }

      window.sessionStorage.setItem(
        SESSION_KEY,
        JSON.stringify(storedSession),
      )
      storedSession = null
    } else if (action === "clear") {
      window.sessionStorage.removeItem(SESSION_KEY)
    } else {
      throw new Error("invalid_action")
    }
  } catch (error) {
    errorCode = "storage_error"
    storedSession = null

    if (action === "read") {
      try {
        window.sessionStorage.removeItem(SESSION_KEY)
      } catch (cleanupError) {
        // 저장소 자체가 차단된 경우에는 정리할 수 없습니다.
      }
    }
  }

  setStateValue("result", {
    command_id: commandId,
    action,
    ok: errorCode === null,
    session: storedSession,
    error_code: errorCode,
  })
}
"""


_AUTH_SESSION_STORAGE = st.components.v2.component(
    "auth_session_storage",
    html=AUTH_SESSION_STORAGE_HTML,
    js=AUTH_SESSION_STORAGE_JS,
)


def render_auth_session_storage(command: dict):
    """브라우저 탭의 인증 세션 저장 명령을 실행합니다."""

    component_state = st.session_state.get(
        "auth_session_storage_component",
        {},
    )
    previous_result = component_state.get("result")
    acknowledged_command_id = None

    if isinstance(previous_result, dict):
        acknowledged_command_id = previous_result.get(
            "command_id"
        )

    return _AUTH_SESSION_STORAGE(
        key="auth_session_storage_component",
        data={
            "command_id": command["command_id"],
            "action": command["action"],
            "session": command.get("session"),
            "acknowledged_command_id": (
                acknowledged_command_id
            ),
        },
        default={
            "result": None,
        },
        on_result_change=lambda: None,
        width="content",
    )


def queue_auth_storage_command(
    action: str,
    session: dict | None = None,
) -> None:
    """브라우저 인증 저장소에 전달할 새 명령을 예약합니다."""

    if action not in {"read", "write", "clear"}:
        raise ValueError("지원하지 않는 인증 저장소 명령입니다.")

    if action == "write" and session is None:
        raise ValueError("저장할 인증 세션이 없습니다.")

    st.session_state[AUTH_STORAGE_COMMAND_KEY] = {
        "command_id": uuid4().hex,
        "action": action,
        "session": session,
    }


def activate_auth_response(response) -> None:
    """로그인 응답을 앱과 브라우저 탭의 인증 상태에 반영합니다."""

    if response.user is None or response.session is None:
        raise RuntimeError("인증 세션이 생성되지 않았습니다.")

    session_tokens = get_session_tokens(
        response.session
    )

    st.session_state.auth_user = response.user
    st.session_state.pop(
        AUTH_STORAGE_SYNCED_TOKEN_KEY,
        None,
    )
    queue_auth_storage_command(
        action="write",
        session=session_tokens,
    )


def get_auth_storage_ack(
    component_result,
    command: dict,
) -> dict | None:
    """현재 브라우저 저장 명령과 일치하는 응답만 반환합니다."""

    result = component_result.get("result")

    if not isinstance(result, dict):
        return None

    if result.get("command_id") != command["command_id"]:
        return None

    if result.get("action") != command["action"]:
        return None

    return result


def _expire_current_auth_session() -> None:
    """만료된 앱 인증 상태를 지우고 브라우저 저장소 삭제를 예약합니다."""

    st.session_state.auth_user = None
    st.session_state.pop(AUTH_STORAGE_SYNCED_TOKEN_KEY, None)
    st.session_state[AUTH_RESTORE_NOTICE_KEY] = (
        "로그인 세션이 만료되어 다시 로그인이 필요합니다."
    )
    queue_auth_storage_command(action="clear")


def _sync_authenticated_session(supabase) -> None:
    """현재 Supabase 세션 토큰을 브라우저 저장 명령과 동기화합니다."""

    if st.session_state.auth_user is None:
        return

    try:
        current_session = supabase.auth.get_session()
        if current_session is None:
            raise RuntimeError("현재 인증 세션이 없습니다.")

        current_tokens = get_session_tokens(current_session)
        current_refresh_token = current_tokens["refresh_token"]
        storage_command = st.session_state[AUTH_STORAGE_COMMAND_KEY]
        pending_session = storage_command.get("session") or {}
        pending_refresh_token = pending_session.get("refresh_token")
        already_pending = (
            storage_command["action"] == "write"
            and pending_refresh_token == current_refresh_token
        )

        if (
            st.session_state.get(AUTH_STORAGE_SYNCED_TOKEN_KEY)
            != current_refresh_token
            and not already_pending
        ):
            queue_auth_storage_command(
                action="write",
                session=current_tokens,
            )
    except Exception as error:
        report_exception("auth.sync_browser_storage", error)
        _expire_current_auth_session()


def _apply_auth_storage_ack(
    command: dict,
    acknowledgement: dict | None,
) -> None:
    """브라우저 저장 명령 성공 결과를 현재 세션 상태에 반영합니다."""

    if acknowledgement is None or not acknowledgement.get("ok"):
        return

    if command["action"] == "write":
        written_session = command.get("session") or {}
        written_refresh_token = written_session.get("refresh_token")
        if isinstance(written_refresh_token, str):
            st.session_state[AUTH_STORAGE_SYNCED_TOKEN_KEY] = (
                written_refresh_token
            )
    elif command["action"] == "clear":
        st.session_state.pop(AUTH_STORAGE_SYNCED_TOKEN_KEY, None)


def _restore_auth_session_from_ack(
    supabase,
    acknowledgement: dict,
) -> None:
    """브라우저에서 읽은 토큰으로 Supabase 인증 세션을 복원합니다."""

    stored_session = acknowledgement.get("session")
    if not isinstance(stored_session, dict):
        return

    try:
        restored_response = restore_session(
            client=supabase,
            access_token=stored_session.get("access_token"),
            refresh_token=stored_session.get("refresh_token"),
        )
        activate_auth_response(restored_response)
        st.rerun()
    except Exception as error:
        report_exception("auth.restore_browser_session", error)
        st.session_state[AUTH_RESTORE_NOTICE_KEY] = (
            "저장된 로그인 정보가 만료되어 다시 로그인이 필요합니다."
        )
        queue_auth_storage_command(action="clear")
        st.rerun()


def _handle_unauthenticated_storage_state(
    supabase,
    command: dict,
    acknowledgement: dict | None,
) -> None:
    """로그아웃 상태에서 저장 명령 대기·복원·후속 읽기를 처리합니다."""

    if st.session_state.auth_user is not None:
        return

    command_action = command["action"]
    if command_action in {"read", "clear"} and acknowledgement is None:
        st.info("저장된 로그인 상태를 확인하고 있습니다...")
        st.stop()

    if (
        command_action == "read"
        and acknowledgement is not None
        and acknowledgement.get("ok")
    ):
        _restore_auth_session_from_ack(supabase, acknowledgement)

    if command_action == "write":
        queue_auth_storage_command(action="read")
        st.rerun()


def _render_auth_storage_notices(
    acknowledgement: dict | None,
) -> None:
    """브라우저 저장 실패와 인증 복원 안내를 한 곳에서 표시합니다."""

    if acknowledgement is not None and not acknowledgement.get("ok"):
        st.warning(
            "브라우저 탭에 로그인 상태를 저장하지 못했습니다. "
            "현재 화면에서는 계속 사용할 수 있지만, "
            "새로고침하면 다시 로그인해야 할 수 있습니다."
        )

    if (
        st.session_state.auth_user is None
        and AUTH_RESTORE_NOTICE_KEY in st.session_state
    ):
        st.warning(st.session_state.pop(AUTH_RESTORE_NOTICE_KEY))


def initialize_auth_session(supabase) -> None:
    """브라우저 탭과 현재 Supabase 인증 세션을 동기화합니다."""

    st.session_state.setdefault("auth_user", None)
    if AUTH_STORAGE_COMMAND_KEY not in st.session_state:
        queue_auth_storage_command(action="read")

    _sync_authenticated_session(supabase)

    command = st.session_state[AUTH_STORAGE_COMMAND_KEY]
    component_result = render_auth_session_storage(command)
    acknowledgement = get_auth_storage_ack(
        component_result=component_result,
        command=command,
    )

    _apply_auth_storage_ack(command, acknowledgement)
    _handle_unauthenticated_storage_state(
        supabase,
        command,
        acknowledgement,
    )
    _render_auth_storage_notices(acknowledgement)


def clear_auth_session_state() -> None:
    """현재 앱 인증 상태를 지우고 브라우저 삭제를 예약합니다."""

    st.session_state.auth_user = None
    st.session_state.pop(
        AUTH_STORAGE_SYNCED_TOKEN_KEY,
        None,
    )
    st.session_state.pop(
        AUTH_RESTORE_NOTICE_KEY,
        None,
    )
    queue_auth_storage_command(action="clear")
