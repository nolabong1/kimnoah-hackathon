import streamlit as st

from models.learning_performance import LearningPerformanceReport
from services.learning_performance_repository import (
    get_learning_performance_data,
)
from services.learning_performance_service import (
    build_learning_performance_html,
    build_learning_performance_report,
    build_performance_highlights,
    summarize_before_after_evidence,
)
from services.presentation_labels import TASK_TYPE_LABELS
from services.study_plan_repository import get_user_study_plans
from services.weekly_review_repository import get_weekly_review_by_plan
from services.weekly_review_service import REFLECTION_QUESTIONS
from views.error_feedback import render_unexpected_error
from views.learning_assessment_state import consume_pending_assessment_plan
from views.learning_assessment_ui import render_learning_assessment_section
from views.study_plan_data_state import get_study_plan_list_snapshot
from views.ui_components import (
    MetricItem,
    render_empty_state,
    render_metric_row,
    render_page_header,
)


PERFORMANCE_PLAN_SELECT_KEY = "learning_performance_plan_id"
def _format_number(value: float | None, suffix: str = "") -> str:
    """선택적인 숫자를 화면용 문자열로 바꿉니다."""

    if value is None:
        return "기록 없음"
    return f"{value:g}{suffix}"


def _render_overview(report: LearningPerformanceReport) -> None:
    """계획의 핵심 실행·평가 지표와 해석 범위를 표시합니다."""

    score_delta = report.average_score_change
    score_delta_text = (
        f"{score_delta:+g}점"
        if score_delta is not None
        else "비교 기록 없음"
    )
    render_metric_row(
        [
            MetricItem(
                "과제 완료율",
                f"{report.completion_rate:g}%",
                icon=":material/task_alt:",
            ),
            MetricItem(
                "완료 과제 기준 예상 학습량",
                f"{report.completed_estimated_minutes}분",
                icon=":material/schedule:",
                help="실제 측정 시간이 아니라 완료한 과제의 예상시간 합계입니다.",
            ),
            MetricItem(
                "최근 퀴즈 평균",
                _format_number(report.average_latest_score, "점"),
                icon=":material/quiz:",
            ),
            MetricItem(
                "첫 응시 대비",
                score_delta_text,
                icon=":material/trending_up:",
            ),
        ]
    )

    with st.container(border=True):
        st.markdown("### 기록에서 확인된 변화")
        for highlight in build_performance_highlights(report):
            st.markdown(f"- {highlight}")

    st.info(
        "이 리포트는 저장된 과제·퀴즈·숙련도 기록을 요약합니다. "
        "완료 과제의 예상시간을 실제 학습시간으로 표현하지 않으며, "
        "점수 변화만으로 학습 효과의 인과관계를 단정하지 않습니다.",
        icon=":material/info:",
    )

    st.subheader("과제 실행 현황")
    render_metric_row(
        [
            MetricItem(
                TASK_TYPE_LABELS[item.task_type],
                f"{item.completed_tasks}/{item.total_tasks}개 완료",
            )
            for item in report.task_type_performance
        ]
    )
    st.progress(
        int(round(report.completion_rate)),
        text=(
            f"전체 {report.total_tasks}개 중 {report.completed_tasks}개 완료 · "
            f"대기 {report.pending_tasks}개 · 건너뜀 {report.skipped_tasks}개"
        ),
    )


def _render_objectives(report: LearningPerformanceReport) -> None:
    """세부 학습목표별 과제 완료와 퀴즈 평가 결과를 표시합니다."""

    if not report.objectives:
        render_empty_state(
            "연결된 세부 학습목표가 없습니다",
            "학습목표 연결 기능 도입 전에 저장한 계획은 전체 성과만 확인할 수 있습니다.",
            icon=":material/flag:",
        )
        return

    for index, objective in enumerate(report.objectives, start=1):
        with st.container(border=True):
            st.caption(f"세부 학습목표 {index}")
            st.markdown(f"### {objective.title}")
            st.progress(
                int(round(objective.completion_rate)),
                text=(
                    f"과제 {objective.completed_task_count}/{objective.task_count}개 완료 · "
                    f"퀴즈 {objective.attempted_quiz_count}/{objective.quiz_count}개 응시"
                ),
            )
            if objective.latest_quiz_average is None:
                st.caption("이 목표에 연결된 퀴즈 응시 기록이 없습니다.")
            else:
                st.caption(
                    "연결 퀴즈 최근 점수 평균 · "
                    f"{objective.latest_quiz_average:g}점"
                )

    if report.unlinked_task_count or report.unlinked_quiz_count:
        st.caption(
            "이전 버전의 미연결 기록 · "
            f"과제 {report.unlinked_task_count}개 · "
            f"퀴즈 {report.unlinked_quiz_count}개"
        )


def _render_quiz_evidence(report: LearningPerformanceReport) -> None:
    """퀴즈별 재응시 점수 흐름을 표시합니다."""

    st.subheader("퀴즈 점수 변화")
    attempted_quizzes = [
        quiz for quiz in report.quizzes if quiz.attempt_count > 0
    ]
    if not attempted_quizzes:
        render_empty_state(
            "아직 퀴즈 응시 기록이 없습니다",
            "이 계획의 퀴즈를 응시하면 첫 점수와 최근 점수를 비교할 수 있습니다.",
            icon=":material/quiz:",
        )
        return

    quiz_columns = st.columns(2, gap="medium")
    for index, quiz in enumerate(attempted_quizzes):
        with quiz_columns[index % 2]:
            with st.container(border=True):
                st.caption(f"{quiz.attempt_count}회 응시")
                st.metric(
                    quiz.title,
                    f"{quiz.latest_score}점",
                    delta=f"첫 응시 대비 {quiz.score_change:+d}점",
                    chart_data=(
                        quiz.score_history
                        if len(quiz.score_history) > 1
                        else None
                    ),
                    chart_type="line",
                )
                st.caption(
                    f"첫 {quiz.first_score}점 · 최고 {quiz.best_score}점"
                )


def _render_before_after_evidence(report: LearningPerformanceReport) -> None:
    """퀴즈 재응시와 문항별 숙련도 변화 근거를 표시합니다."""

    st.subheader("퀴즈·숙련도 변화")
    summary = summarize_before_after_evidence(report)
    render_metric_row(
        [
            MetricItem(
                "첫 퀴즈 응시 평균",
                _format_number(report.average_first_score, "점"),
                icon=":material/flag:",
            ),
            MetricItem(
                "최근 퀴즈 응시 평균",
                _format_number(report.average_latest_score, "점"),
                icon=":material/trending_up:",
            ),
            MetricItem(
                "숙련도 상승 개념",
                (
                    f"{summary['improved_concept_count']}/"
                    f"{summary['evaluated_concept_count']}개"
                ),
                icon=":material/psychology:",
            ),
            MetricItem(
                "60점 기준 신규 도달",
                f"{summary['score_threshold_reached_count']}개",
                icon=":material/ads_click:",
                help=(
                    "첫 평가 직전에는 60점 미만이었고 마지막 평가 직후에는 "
                    "60점 이상인 개념 수입니다. 취약 판정 해제를 의미하지는 않습니다."
                ),
            ),
        ]
    )
    st.caption(
        "퀴즈 평균은 각 퀴즈의 첫 응시와 최근 응시를 비교합니다. 개념 숙련도는 "
        "이 계획 퀴즈 문항의 첫 응시 직전과 마지막 응시 직후를 비교하며, 변화와 "
        "학습의 인과관계를 단정하지 않습니다."
    )


def _render_concept_evidence(report: LearningPerformanceReport) -> None:
    """선택 계획의 문항에서 발생한 개념별 숙련도 변화를 표시합니다."""

    st.subheader("개념별 숙련도 근거")
    if not report.concepts:
        render_empty_state(
            "아직 개념 숙련도 변화가 없습니다",
            "개념 태그가 연결된 퀴즈를 응시하면 문항별 변화가 기록됩니다.",
            icon=":material/monitoring:",
        )
        return

    rows = [
        {
            "개념": concept.concept_name,
            "평가 문항": concept.assessed_question_count,
            "정답": concept.correct_count,
            "오답": concept.incorrect_count,
            "첫 평가 직전": concept.first_score_before,
            "마지막 평가 직후": concept.last_score_after,
            "계획 문항 증감": f"{concept.plan_score_delta:+d}점",
            "현재 숙련도": concept.current_score,
            "현재 상태": (
                "취약"
                if concept.current_is_weak is True
                else "학습 중"
                if concept.current_is_weak is False
                else "확인 불가"
            ),
        }
        for concept in report.concepts
    ]
    st.dataframe(
        rows,
        hide_index=True,
        column_config={
            "평가 문항": st.column_config.NumberColumn(format="%d개"),
            "정답": st.column_config.NumberColumn(format="%d개"),
            "오답": st.column_config.NumberColumn(format="%d개"),
            "첫 평가 직전": st.column_config.ProgressColumn(
                min_value=0,
                max_value=100,
                format="%d점",
            ),
            "마지막 평가 직후": st.column_config.ProgressColumn(
                min_value=0,
                max_value=100,
                format="%d점",
            ),
            "현재 숙련도": st.column_config.ProgressColumn(
                min_value=0,
                max_value=100,
                format="%d점",
            ),
        },
    )
    st.caption(
        "계획 문항 증감은 이 계획에 연결된 퀴즈 문항의 score_delta 합계입니다. "
        "현재 숙련도에는 같은 과목의 다른 계획에서 발생한 이후 평가도 포함될 수 있습니다."
    )


def _render_weekly_review_evidence(existing_review: dict | None) -> None:
    """사용자가 작성하고 저장한 주간 회고를 정성 근거로 표시합니다."""

    st.subheader("주간 회고 근거")
    if existing_review is None:
        render_empty_state(
            "저장된 주간 회고가 없습니다",
            "계획이 종료되거나 모든 과제를 완료하면 주간 학습 회고에서 정성 기록을 남길 수 있습니다.",
            icon=":material/rate_review:",
        )
        return

    reflection_answers = existing_review.get("reflection_answers")
    if not isinstance(reflection_answers, dict):
        reflection_answers = {}
    meaningful_answers = [
        (question, str(reflection_answers.get(key, "")).strip())
        for key, question in REFLECTION_QUESTIONS.items()
        if str(reflection_answers.get(key, "")).strip()
    ]

    st.markdown("#### 학생이 직접 작성한 회고")
    if meaningful_answers:
        for question, answer in meaningful_answers:
            with st.container(border=True):
                st.markdown(f"**{question}**")
                st.write(answer)
    else:
        st.caption("저장된 직접 회고 답변이 없습니다.")

    st.markdown("#### AI 회고 분석")
    with st.container(border=True):
        st.caption(
            f"저장된 회고 · {existing_review.get('week_start')} ~ "
            f"{existing_review.get('week_end')}"
        )
        st.markdown(existing_review.get("ai_review_markdown") or "회고 내용이 없습니다.")


def _render_report_download(
    report: LearningPerformanceReport,
    existing_review: dict | None,
) -> None:
    """현재 리포트를 추가 조회 없이 독립 HTML 파일로 제공합니다."""

    review = existing_review or {}
    reflection_answers = review.get("reflection_answers")
    if not isinstance(reflection_answers, dict):
        reflection_answers = {}
    report_html = build_learning_performance_html(
        report,
        reflection_answers=reflection_answers,
        ai_review_markdown=review.get("ai_review_markdown"),
    )
    st.download_button(
        "읽기 쉬운 HTML 리포트 내려받기",
        data=report_html.encode("utf-8-sig"),
        file_name=(
            "학습성과_리포트_"
            f"{report.plan_start_date.isoformat()}_"
            f"{report.plan_target_date.isoformat()}_"
            f"{report.plan_id[:8]}.html"
        ),
        mime="text/html; charset=utf-8",
        key=f"learning_performance_download_{report.plan_id}",
        help="브라우저에서 바로 읽고 인쇄하거나 PDF로 저장할 수 있습니다.",
        icon=":material/download:",
        on_click="ignore",
    )


def render_learning_performance(supabase, user) -> None:
    """저장된 계획 하나의 실행·평가·숙련도 성과를 표시합니다."""

    render_page_header(
        "학습 성과 리포트",
        "계획 실행, 퀴즈 재응시, 개념 숙련도 변화를 하나의 근거로 확인하세요.",
    )

    try:
        plans = get_study_plan_list_snapshot(
            supabase,
            str(user.id),
            st.session_state,
            loader=lambda: get_user_study_plans(
                supabase=supabase,
                user_id=str(user.id),
            ),
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="learning_performance.load_plans",
            user_message=(
                "학습 성과를 확인할 계획을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not plans:
        render_empty_state(
            "아직 저장된 학습계획이 없습니다",
            "계획을 만들고 과제와 퀴즈를 진행하면 학습 성과가 여기에 표시됩니다.",
            icon=":material/analytics:",
        )
        return

    plans_by_id = {str(plan["id"]): plan for plan in plans}
    plan_options = list(plans_by_id)
    pending_plan_id = consume_pending_assessment_plan(st.session_state)
    if pending_plan_id in plans_by_id:
        st.session_state[PERFORMANCE_PLAN_SELECT_KEY] = pending_plan_id
    selected_state = st.session_state.get(PERFORMANCE_PLAN_SELECT_KEY)
    if selected_state not in plan_options:
        st.session_state.pop(PERFORMANCE_PLAN_SELECT_KEY, None)

    selected_plan_id = st.selectbox(
        "성과를 확인할 계획",
        options=plan_options,
        format_func=lambda plan_id: (
            f"{plans_by_id[plan_id]['title']} · "
            f"{plans_by_id[plan_id]['course_name']} · "
            f"{plans_by_id[plan_id]['start_date']}"
        ),
        key=PERFORMANCE_PLAN_SELECT_KEY,
    )

    try:
        with st.skeleton(height=240):
            performance_data = get_learning_performance_data(
                supabase=supabase,
                user_id=str(user.id),
                plan_id=selected_plan_id,
            )
            report = build_learning_performance_report(performance_data)
            existing_review = get_weekly_review_by_plan(
                supabase=supabase,
                user_id=str(user.id),
                plan_id=selected_plan_id,
            )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="learning_performance.load_report",
            user_message=(
                "선택한 계획의 학습 성과를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    st.caption(
        f"{report.course_name} · {report.plan_start_date.isoformat()} ~ "
        f"{report.plan_target_date.isoformat()}"
    )
    st.subheader(report.plan_title)
    _render_report_download(report, existing_review)

    assessment_tab, overview_tab, objective_tab, evidence_tab = st.tabs(
        ["학습 전·후 평가", "성과 요약", "학습목표별 성과", "성장 근거"]
    )
    with assessment_tab:
        render_learning_assessment_section(
            supabase=supabase,
            user=user,
            plan=performance_data["plan"],
            objectives=performance_data["objectives"],
        )
    with overview_tab:
        _render_overview(report)
    with objective_tab:
        _render_objectives(report)
    with evidence_tab:
        _render_before_after_evidence(report)
        _render_quiz_evidence(report)
        _render_concept_evidence(report)
        _render_weekly_review_evidence(existing_review)
