import streamlit as st


@st.dialog("🎉 과제 완료!")
def show_completion_dialog(
    message,
    daily_bonus_exp,
):
    st.success(message)

    if daily_bonus_exp > 0:
        st.markdown("### 오늘의 학습 목표 달성!")
        st.write(
            "오늘 예정된 과제를 모두 완료해서 "
            f"보너스 EXP {daily_bonus_exp}을 획득했습니다."
        )
    else:
        st.write(
            "좋아요! 다음 과제도 이어서 완료해보세요."
        )

    if st.button(
        "확인",
        type="primary",
        use_container_width=True,
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