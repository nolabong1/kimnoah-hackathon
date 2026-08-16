import streamlit as st

from services.auth_service import (
    sign_in,
    sign_out,
    sign_up,
)
from services.profile_service import get_profile
from services.supabase_client import get_supabase_client

from views.auth_session_storage import (
    activate_auth_response,
    clear_auth_session_state,
    initialize_auth_session,
)
from views.saved_plans_view import render_saved_plans
from views.create_plan_view import render_create_plan
from views.dashboard_view import render_dashboard
from views.source_review_material_view import (
    SOURCE_REVIEW_SESSION_KEYS,
    render_source_review_material,
)
from views.tutor_state import clear_tutor_state
from views.tutor_view import render_tutor

st.set_page_config(
    page_title="AI 학습 코치",
    page_icon="🎓",
    layout="centered",
)

supabase = get_supabase_client()

st.title("🎓 AI 학습 코치")
st.write("나의 목표와 수준에 맞는 학습계획을 만들어보세요.")
initialize_auth_session(supabase)


# 로그인하지 않은 사용자에게 인증 화면 표시
if st.session_state.auth_user is None:
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("이메일")
            login_password = st.text_input("비밀번호", type="password")
            login_submitted = st.form_submit_button("로그인")

        if login_submitted:
            try:
                response = sign_in(
                    supabase,
                    login_email,
                    login_password,
                )
                activate_auth_response(response)
                st.rerun()
            except Exception as error:
                st.error(f"로그인에 실패했습니다: {error}")

    with signup_tab:
        with st.form("signup_form"):
            nickname = st.text_input("닉네임", max_chars=30)
            signup_email = st.text_input("이메일")
            signup_password = st.text_input(
                "비밀번호",
                type="password",
                help="8자 이상 입력해주세요.",
            )
            password_confirm = st.text_input(
                "비밀번호 확인",
                type="password",
            )
            signup_submitted = st.form_submit_button("회원가입")

        if signup_submitted:
            if not nickname.strip():
                st.warning("닉네임을 입력해주세요.")
            elif "@" not in signup_email:
                st.warning("올바른 이메일을 입력해주세요.")
            elif len(signup_password) < 8:
                st.warning("비밀번호는 8자 이상이어야 합니다.")
            elif signup_password != password_confirm:
                st.warning("비밀번호가 일치하지 않습니다.")
            else:
                try:
                    response = sign_up(
                        supabase,
                        nickname,
                        signup_email,
                        signup_password,
                    )

                    if response.session is None:
                        st.success(
                            "회원가입이 완료되었습니다. "
                            "이메일 확인 후 로그인해주세요."
                        )
                    else:
                        activate_auth_response(response)
                        st.rerun()
                except Exception as error:
                    st.error(f"회원가입에 실패했습니다: {error}")

    st.stop()


# 로그인한 사용자의 프로필 조회
user = st.session_state.auth_user

try:
    profile = get_profile(supabase, user.id)
except Exception as error:
    st.error(f"프로필을 불러오지 못했습니다: {error}")
    st.stop()


with st.sidebar:
    st.write(f"**{profile['nickname']}**")
    st.metric("레벨", profile["level"])
    st.metric("총 EXP", profile["total_exp"])
    st.metric("연속 학습", f"{profile['current_streak']}일")

    selected_page = st.radio(
        "메뉴",
        options=[
            "오늘 학습",
            "계획 만들기",
            "저장된 계획",
            "AI 복습 자료 만들기",
            "단계별 힌트 AI 튜터",
        ],
        key="main_navigation",
    )

    st.divider()
    if st.button("로그아웃"):
        sign_out(supabase)

        for key in [
            "generated_plan",
            "generated_plan_start_date",
            "generated_plan_metadata",
            "generated_plan_saved",
            "saved_plan_id",
            *SOURCE_REVIEW_SESSION_KEYS,
        ]:
            st.session_state.pop(key, None)

        clear_tutor_state(st.session_state)

        clear_auth_session_state()
        st.rerun()


st.success(f"{profile['nickname']}님, 환영합니다!")

if selected_page == "오늘 학습":
    render_dashboard(
        supabase=supabase,
        user=user,
    )

elif selected_page == "계획 만들기":
    render_create_plan(
        supabase=supabase,
        user=user,
    )

elif selected_page == "저장된 계획":
    render_saved_plans(
        supabase=supabase,
        user=user,
    )

elif selected_page == "AI 복습 자료 만들기":
    render_source_review_material(
        supabase=supabase,
        user=user,
    )

else:
    render_tutor(
        supabase=supabase,
        user=user,
    )
