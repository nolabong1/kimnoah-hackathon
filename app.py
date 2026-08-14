import streamlit as st


# 브라우저 탭과 화면의 기본 설정
st.set_page_config(
    page_title="AI 학습 코치",
    page_icon="🎓",
    layout="centered",
)


# 서비스의 첫 화면
st.title("🎓 AI 학습 코치")
st.write("나의 목표와 수준에 맞는 학습계획을 만들어보세요.")

study_goal = st.text_input(
    "학습 목표",
    placeholder="예: 한 달 동안 파이썬 기초 공부하기",
)

if st.button("학습계획 만들기"):
    if study_goal.strip():
        st.success(f"'{study_goal}' 학습계획 생성을 준비했습니다!")
    else:
        st.warning("먼저 학습 목표를 입력해주세요.")