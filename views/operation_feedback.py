from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import streamlit as st


@contextmanager
def operation_status(
    running_label: str,
    success_label: str,
    error_label: str,
) -> Iterator[Any]:
    """여러 단계의 긴 작업을 완료·실패 상태까지 같은 영역에 표시합니다."""

    status = st.status(
        running_label,
        state="running",
        expanded=True,
        width="stretch",
    )
    try:
        yield status
    except Exception:
        status.update(
            label=error_label,
            state="error",
            expanded=True,
        )
        raise
    else:
        status.update(
            label=success_label,
            state="complete",
            expanded=False,
        )
