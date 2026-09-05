import streamlit as st

from views.interaction_feedback import render_interaction_event_batch
from views.interaction_state import pop_completion_interaction_events
from views.weekly_review_state import request_weekly_review_navigation


def render_weekly_review_continuation_card(
    *,
    plan_id: str,
    plan_title: str,
    widget_scope: str,
) -> None:
    """완료한 7일 계획을 회고와 다음 계획으로 연결하는 안내를 표시합니다."""

    with st.container(border=True):
        st.markdown("#### 다음 7일도 이어서 학습해볼까요?")
        st.caption(
            f"‘{plan_title}’의 기록을 회고하면 AI 추천을 반영한 "
            "다음 7일 계획을 바로 만들 수 있습니다."
        )
        if st.button(
            "회고하고 다음 계획 이어가기",
            key=f"{widget_scope}_continue_weekly_review_{plan_id}",
            type="primary",
            icon=":material/arrow_forward:",
            width="stretch",
        ):
            request_weekly_review_navigation(st.session_state, plan_id)
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
