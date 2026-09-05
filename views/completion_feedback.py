import streamlit as st

from views.interaction_feedback import render_interaction_event_batch
from views.interaction_state import pop_completion_interaction_events
from views.learning_assessment_state import (
    request_learning_assessment_navigation,
)
from views.weekly_review_state import request_weekly_review_navigation


def render_weekly_review_continuation_card(
    *,
    plan_id: str,
    plan_title: str,
    widget_scope: str,
) -> None:
    """완료 계획을 사후 평가와 회고·다음 계획으로 연결합니다."""

    with st.container(border=True):
        st.markdown("#### 학습 결과를 확인하고 다음 7일로 이어가세요")
        st.caption(
            f"‘{plan_title}’의 사후 평가에서 학습 전후 변화를 확인한 뒤 "
            "주간 회고와 다음 계획으로 이어갈 수 있습니다."
        )
        if st.button(
            "사후 평가 확인하기",
            key=f"{widget_scope}_continue_assessment_{plan_id}",
            type="primary",
            icon=":material/assignment_turned_in:",
            width="stretch",
        ):
            request_learning_assessment_navigation(st.session_state, plan_id)
            st.rerun()
        if st.button(
            "회고로 바로가기",
            key=f"{widget_scope}_continue_weekly_review_{plan_id}",
            type="tertiary",
            icon=":material/rate_review:",
            width="stretch",
        ):
            request_weekly_review_navigation(st.session_state, plan_id)
            st.rerun()


def render_learning_assessment_entry_card(
    *,
    plan_id: str,
    widget_scope: str,
) -> None:
    """진행 중인 계획에서 학습 전·후 평가로 이동하는 짧은 안내입니다."""

    with st.container(border=True):
        st.markdown("#### 학습 전·후 변화를 남겨보세요")
        st.caption(
            "학습 시작 전 진단을 준비하면 계획 종료 후 같은 목표의 "
            "사후 평가와 비교할 수 있습니다."
        )
        if st.button(
            "학습 전·후 평가 열기",
            key=f"{widget_scope}_open_assessment_{plan_id}",
            icon=":material/assignment:",
            width="stretch",
        ):
            request_learning_assessment_navigation(st.session_state, plan_id)
            st.rerun()


@st.dialog("과제 완료")
def show_completion_dialog(
    message,
    daily_bonus_exp,
    next_task_title=None,
    guided_flow=False,
    interaction_events=None,
    completed_plan_id=None,
    completed_plan_title=None,
):
    render_interaction_event_batch(
        interaction_events,
        placement="inline",
    )
    st.success(message, icon=":material/task_alt:")

    if daily_bonus_exp > 0:
        with st.container(border=True):
            st.caption("오늘의 추가 보상")
            st.metric("일일 완료 보너스", f"+{daily_bonus_exp} EXP")
            st.write("오늘 예정된 과제를 모두 완료했습니다.")
    else:
        if next_task_title:
            st.caption(f"다음 과제 · {next_task_title}")
        else:
            st.caption("학습 기록이 저장되었습니다.")

    if completed_plan_id and completed_plan_title:
        render_weekly_review_continuation_card(
            plan_id=str(completed_plan_id),
            plan_title=str(completed_plan_title),
            widget_scope="completion_dialog",
        )
        if st.button(
            "나중에 하기",
            key=f"completion_dialog_dismiss_{completed_plan_id}",
            type="tertiary",
            width="stretch",
        ):
            st.rerun()
        return

    if next_task_title:
        button_label = "다음 과제 이어하기"
        button_icon = ":material/arrow_forward:"
    elif guided_flow and daily_bonus_exp > 0:
        button_label = "오늘 학습 마치기"
        button_icon = ":material/done_all:"
    elif guided_flow:
        button_label = "학습 화면으로 돌아가기"
        button_icon = ":material/arrow_back:"
    else:
        button_label = "확인"
        button_icon = ":material/check:"

    if st.button(
        button_label,
        type="primary",
        icon=button_icon,
        width="stretch",
    ):
        st.rerun()


def render_completion_feedback():
    feedback = st.session_state.pop(
        "task_completion_feedback",
        None,
    )

    if feedback is None:
        return

    message = feedback["message"]
    daily_bonus_exp = feedback.get(
        "daily_bonus_exp",
        0,
    )
    interaction_events = pop_completion_interaction_events(
        st.session_state
    )

    st.toast(
        message,
        icon="🎉",
    )

    show_completion_dialog(
        message=message,
        daily_bonus_exp=daily_bonus_exp,
        next_task_title=feedback.get("next_task_title"),
        guided_flow=feedback.get("guided_flow", False),
        interaction_events=interaction_events,
        completed_plan_id=feedback.get("completed_plan_id"),
        completed_plan_title=feedback.get("completed_plan_title"),
    )
