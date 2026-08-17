import streamlit as st


@st.dialog("과제 완료")
def show_completion_dialog(
    message,
    daily_bonus_exp,
):
    st.success(message, icon=":material/task_alt:")

    if daily_bonus_exp > 0:
        with st.container(border=True):
            st.caption("오늘의 추가 보상")
            st.metric("일일 완료 보너스", f"+{daily_bonus_exp} EXP")
            st.write("오늘 예정된 과제를 모두 완료했습니다.")
    else:
        st.caption("다음 과제도 이어서 완료해보세요.")

    if st.button(
        "확인",
        type="primary",
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

    st.toast(
        message,
        icon="🎉",
    )

    if daily_bonus_exp > 0:
        st.balloons()

    show_completion_dialog(
        message=message,
        daily_bonus_exp=daily_bonus_exp,
    )
