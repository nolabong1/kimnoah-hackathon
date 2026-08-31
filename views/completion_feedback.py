import streamlit as st

from views.interaction_feedback import render_interaction_event_batch
from views.interaction_state import pop_completion_interaction_events


@st.dialog("과제 완료")
def show_completion_dialog(
    message,
    daily_bonus_exp,
    next_task_title=None,
    guided_flow=False,
    interaction_events=None,
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
    )
