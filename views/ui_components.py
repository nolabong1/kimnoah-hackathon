from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import streamlit as st


DASHBOARD_CONTENT_WIDTH = 1280
STANDARD_CONTENT_WIDTH = 1120
READING_CONTENT_WIDTH = 900
AUTH_CONTENT_WIDTH = 520


@dataclass(frozen=True)
class MetricItem:
    """대시보드 메트릭 하나의 표시 정보를 정의합니다."""

    label: str
    value: str
    icon: str | None = None
    help: str | None = None


@contextmanager
def content_frame(
    width: int = DASHBOARD_CONTENT_WIDTH,
) -> Iterator[None]:
    """페이지 콘텐츠를 지정 폭의 중앙 정렬 영역에 표시합니다."""

    if width <= 0:
        raise ValueError("콘텐츠 폭은 1px 이상이어야 합니다.")

    with st.container(horizontal_alignment="center"):
        with st.container(
            width=width,
            horizontal_alignment="left",
        ):
            yield


def render_page_header(
    title: str,
    description: str,
) -> None:
    """일관된 제목과 한 줄 설명으로 페이지를 시작합니다."""

    st.title(title)
    st.caption(description)


def render_metric_row(
    metrics: Sequence[MetricItem],
) -> None:
    """메트릭을 줄바꿈 가능한 가로 카드 행으로 표시합니다."""

    if not metrics:
        return

    with st.container(horizontal=True, gap="small"):
        for metric in metrics:
            st.metric(
                metric.label,
                metric.value,
                icon=metric.icon,
                help=metric.help,
                border=True,
            )


def render_empty_state(
    title: str,
    description: str,
    *,
    icon: str = ":material/inbox:",
) -> None:
    """비어 있는 화면의 이유와 다음 행동을 가벼운 카드로 안내합니다."""

    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.caption(description)
