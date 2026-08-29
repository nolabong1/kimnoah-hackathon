import streamlit as st

from models.learning_objective import LearningObjectiveConnectionReport
from services.learning_objective_connection_service import (
    build_learning_objective_connection_report,
)
from services.learning_objective_repository import (
    get_learning_objective_connection_data,
)
from views.error_feedback import render_unexpected_error
from views.ui_components import MetricItem, render_metric_row


def _render_title_list(title: str, values: list[str], empty_message: str) -> None:
    """연결 제목 목록을 짧은 읽기 전용 영역으로 표시합니다."""

    st.markdown(f"**{title}**")
    if not values:
        st.caption(empty_message)
        return
    for value in values:
        st.write(f"- {value}")


def _render_unlinked_notice(report: LearningObjectiveConnectionReport) -> None:
    """기능 도입 전 생성되어 목표 연결이 없는 데이터만 별도로 안내합니다."""

    unlinked_count = sum(
        (
            report.unlinked_task_count,
            report.unlinked_source_material_count,
            report.unlinked_review_material_count,
            report.unlinked_quiz_count,
        )
    )
    if unlinked_count == 0:
        return

    st.info(
        "학습목표 연결 기능 도입 전에 만든 항목 "
        f"{unlinked_count}개는 목표별 집계에서 제외했습니다. "
        "자료나 퀴즈를 다시 생성하면 현재 과제 목표에 연결됩니다.",
        icon=":material/info:",
    )


def render_learning_objective_connections(
    *,
    supabase,
    user_id: str,
    plan_id: str,
    tasks: list[dict],
) -> None:
    """저장된 계획의 목표별 과제·자료·퀴즈 연결을 지연 조회해 표시합니다."""

    connection_open = st.toggle(
        "학습목표 연결 보기",
        key=f"saved_plan_objective_connections_{plan_id}",
        help="목표별로 연결된 과제, 학습자료와 퀴즈를 확인합니다.",
        persist_state="session",
    )
    if not connection_open:
        return

    try:
        with st.spinner("학습목표 연결을 확인하고 있습니다..."):
            connection_data = get_learning_objective_connection_data(
                supabase=supabase,
                user_id=user_id,
                plan_id=plan_id,
            )
            report = build_learning_objective_connection_report(
                objectives=connection_data["objectives"],
                tasks=tasks,
                learning_materials=connection_data["learning_materials"],
                review_materials=connection_data["review_materials"],
                quizzes=connection_data["quizzes"],
            )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="saved_plans.load_objective_connections",
            user_message=(
                "학습목표 연결을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not report.summaries:
        st.info(
            "이 계획에는 표시할 학습목표가 없습니다.",
            icon=":material/info:",
        )
        return

    st.subheader("학습목표 연결")
    st.caption(
        "각 목표를 어떤 과제로 학습하고, 어떤 자료와 퀴즈가 같은 목표를 "
        "사용하는지 보여줍니다."
    )
    _render_unlinked_notice(report)

    for summary in report.summaries:
        objective = summary.objective
        material_count = (
            len(summary.source_material_titles)
            + len(summary.review_material_titles)
        )
        with st.container(border=True):
            st.markdown(f"#### {objective.sort_order}. {objective.title}")
            st.write(objective.description)
            render_metric_row(
                [
                    MetricItem("연결 과제", f"{len(summary.task_titles)}개"),
                    MetricItem(
                        "학습자료",
                        f"{material_count}개",
                    ),
                    MetricItem("퀴즈", f"{len(summary.quiz_titles)}개"),
                ]
            )

            task_column, material_column, quiz_column = st.columns(3)
            with task_column:
                _render_title_list(
                    "연결 과제",
                    summary.task_titles,
                    "연결된 과제가 없습니다.",
                )
            with material_column:
                _render_title_list(
                    "원본 자료",
                    summary.source_material_titles,
                    "연결된 원본이 없습니다.",
                )
                _render_title_list(
                    "AI 학습자료",
                    summary.review_material_titles,
                    "연결된 AI 자료가 없습니다.",
                )
            with quiz_column:
                _render_title_list(
                    "퀴즈",
                    summary.quiz_titles,
                    "연결된 퀴즈가 없습니다.",
                )
