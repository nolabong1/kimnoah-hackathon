import streamlit as st

from services.error_reporting import report_exception


def render_unexpected_error(
    error: Exception,
    *,
    operation: str,
    user_message: str,
) -> str:
    """내부 예외는 기록하고 사용자에게 안전한 오류 문구만 표시합니다."""

    error_id = report_exception(operation, error)
    st.error(f"{user_message}\n\n오류 ID: `{error_id}`")
    return error_id


def render_unexpected_warning(
    error: Exception,
    *,
    operation: str,
    user_message: str,
) -> str:
    """대체 흐름으로 복구한 예외를 경고 수준의 UI로 표시합니다."""

    error_id = report_exception(operation, error)
    st.warning(f"{user_message}\n\n오류 ID: `{error_id}`")
    return error_id
