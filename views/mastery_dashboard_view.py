from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.concept_mastery_repository import (
    get_user_concept_masteries,
)
from services.concept_mastery_service import (
    summarize_course_masteries,
)
from views.ui_components import (
    MetricItem,
    render_empty_state,
    render_metric_row,
    render_page_header,
)


MASTERY_COURSE_SELECT_KEY = "mastery_dashboard_course_key"
MASTERY_FILTER_KEY = "mastery_dashboard_concept_filter"
SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")


def _format_last_assessed_at(value: str | None) -> str:
    """마지막 평가 시각을 서울 기준으로 표시합니다."""

    if not value:
        return "평가 기록 없음"

    assessed_at = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    return assessed_at.astimezone(SEOUL_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M"
    )


def _render_course_comparison(
    course_summaries: list[dict],
) -> None:
    """평가된 과목의 평균 숙련도를 비교해 표시합니다."""

    st.subheader("과목 비교")
    chart_data = {
        "과목": [
            summary["course_name"]
            for summary in course_summaries
        ],
        "평균 숙련도": [
            summary["average_mastery_score"]
            for summary in course_summaries
        ],
    }
    st.bar_chart(
        chart_data,
        x="과목",
        y="평균 숙련도",
        horizontal=True,
        sort=False,
        height=max(220, len(course_summaries) * 55),
    )
    st.caption(
        "평균 숙련도는 해당 과목에서 퀴즈로 평가된 개념의 현재 점수 평균입니다."
    )


def _render_concept_mastery(mastery: dict) -> None:
    """개념 하나의 현재 숙련도와 누적 결과를 표시합니다."""

    mastery_score = mastery["mastery_score"]

    with st.container(border=True):
        st.caption("취약 개념" if mastery["is_weak"] else "학습 중인 개념")
        st.markdown(f"### {mastery['concept_name']}")
        st.progress(
            mastery_score,
            text=f"숙련도 {mastery_score}/100",
        )
        st.caption(
            f"누적 정답 {mastery['correct_count']}회 · "
            f"누적 오답 {mastery['incorrect_count']}회 · "
            "연속 오답 "
            f"{mastery['consecutive_incorrect_count']}회"
        )
        st.caption(
            "최근 평가 · "
            + _format_last_assessed_at(
                mastery.get("last_assessed_at")
            )
        )

        if mastery["is_weak"]:
            st.warning("현재 복습이 필요한 취약 개념입니다.")
        else:
            st.caption("현재 취약 기준 이상입니다.")


def render_mastery_dashboard(
    supabase,
    user,
) -> None:
    """로그인 사용자의 과목별 개념 숙련도 화면을 표시합니다."""

    render_page_header(
        "과목별 숙련도",
        "퀴즈 결과로 갱신된 숙련도를 비교하고 보완할 개념을 확인합니다.",
    )

    try:
        concept_masteries = get_user_concept_masteries(
            supabase=supabase,
            user_id=str(user.id),
        )
        course_summaries = summarize_course_masteries(
            concept_masteries
        )
    except Exception as error:
        st.error(f"과목별 숙련도를 불러오지 못했습니다: {error}")
        return

    if not concept_masteries:
        render_empty_state(
            "아직 평가된 개념이 없습니다",
            "개념 태그가 포함된 퀴즈를 응시하면 과목별 숙련도가 표시됩니다.",
            icon=":material/monitoring:",
        )
        return

    weak_concept_count = sum(
        mastery["is_weak"] for mastery in concept_masteries
    )
    overall_average = round(
        sum(
            mastery["mastery_score"]
            for mastery in concept_masteries
        )
        / len(concept_masteries),
        1,
    )

    render_metric_row(
        [
            MetricItem("평가된 과목", f"{len(course_summaries)}개"),
            MetricItem("평가된 개념", f"{len(concept_masteries)}개"),
            MetricItem("전체 개념 평균", f"{overall_average}점"),
            MetricItem("현재 취약 개념", f"{weak_concept_count}개"),
        ]
    )

    summaries_by_key = {
        summary["course_key"]: summary
        for summary in course_summaries
    }
    course_options = list(summaries_by_key)
    selected_course_state = st.session_state.get(
        MASTERY_COURSE_SELECT_KEY
    )

    if (
        selected_course_state is not None
        and selected_course_state not in course_options
    ):
        st.session_state.pop(MASTERY_COURSE_SELECT_KEY, None)

    comparison_tab, detail_tab = st.tabs(["과목 비교", "개념 상세"])
    with comparison_tab:
        _render_course_comparison(course_summaries)

    with detail_tab:
        selected_course_key = st.selectbox(
            "자세히 볼 과목",
            options=course_options,
            format_func=lambda course_key: summaries_by_key[
                course_key
            ]["course_name"],
            key=MASTERY_COURSE_SELECT_KEY,
        )
        selected_summary = summaries_by_key[selected_course_key]
        selected_masteries = [
            mastery
            for mastery in concept_masteries
            if mastery["course_key"] == selected_course_key
        ]

        st.subheader(selected_summary["course_name"])
        render_metric_row(
            [
                MetricItem(
                    "평균 숙련도",
                    f"{selected_summary['average_mastery_score']}점",
                ),
                MetricItem(
                    "평가된 개념",
                    f"{selected_summary['evaluated_concept_count']}개",
                ),
                MetricItem(
                    "취약 개념",
                    f"{selected_summary['weak_concept_count']}개",
                ),
                MetricItem(
                    "누적 정답 / 오답",
                    (
                        f"{selected_summary['correct_count']} / "
                        f"{selected_summary['incorrect_count']}"
                    ),
                ),
            ]
        )

        st.caption(
            "과목 최근 평가 · "
            + _format_last_assessed_at(
                selected_summary.get("last_assessed_at")
            )
        )
        selected_filter = st.segmented_control(
            "개념 보기",
            options=["전체", "취약 개념"],
            default="전체",
            key=MASTERY_FILTER_KEY,
        )
        visible_masteries = (
            [
                mastery
                for mastery in selected_masteries
                if mastery["is_weak"]
            ]
            if selected_filter == "취약 개념"
            else selected_masteries
        )

        if not visible_masteries:
            st.success("이 과목에는 현재 취약 개념이 없습니다.")
            return

        concept_columns = st.columns(2, gap="medium")
        for index, mastery in enumerate(visible_masteries):
            with concept_columns[index % 2]:
                _render_concept_mastery(mastery)
