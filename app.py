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
from views.gamification_state import (
    PENDING_NAVIGATION_KEY as GAMIFICATION_PENDING_NAVIGATION_KEY,
    clear_gamification_state,
)
from views.gamification_view import (
    render_gamification_notifications,
    render_gamification_page,
)
from views.mastery_dashboard_view import render_mastery_dashboard
from views.shop_state import clear_shop_state
from views.source_review_material_view import (
    SOURCE_REVIEW_SESSION_KEYS,
    render_source_review_material,
)
from views.tutor_state import clear_tutor_state
from views.tutor_view import render_tutor
from views.test_tools_view import (
    clear_test_tools_state,
    render_sidebar_test_tools,
)
from views.ui_components import (
    AUTH_CONTENT_WIDTH,
    DASHBOARD_CONTENT_WIDTH,
    STANDARD_CONTENT_WIDTH,
    content_frame,
)
from views.weekly_review_state import (
    PENDING_NAVIGATION_KEY as WEEKLY_REVIEW_PENDING_NAVIGATION_KEY,
    clear_weekly_review_state,
)
from views.weekly_review_view import render_weekly_review

st.set_page_config(
    page_title="AI 학습 코치",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

supabase = get_supabase_client()

initialize_auth_session(supabase)


# 로그인하지 않은 사용자에게 인증 화면 표시
if st.session_state.auth_user is None:
    with content_frame(AUTH_CONTENT_WIDTH):
        with st.container(border=True):
            st.title("🎓 AI 학습 코치")
            st.caption("나의 목표와 수준에 맞는 학습계획을 만들어보세요.")

            login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

            with login_tab:
                with st.form("login_form"):
                    login_email = st.text_input("이메일")
                    login_password = st.text_input(
                        "비밀번호",
                        type="password",
                    )
                    login_submitted = st.form_submit_button(
                        "로그인",
                        type="primary",
                        width="stretch",
                    )

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
                    signup_submitted = st.form_submit_button(
                        "회원가입",
                        type="primary",
                        width="stretch",
                    )

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


def show_dashboard() -> None:
    """오늘 학습 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_dashboard(
            supabase=supabase,
            user=user,
        )


def show_create_plan() -> None:
    """학습계획 생성 화면을 표시합니다."""

    with content_frame(STANDARD_CONTENT_WIDTH):
        render_create_plan(
            supabase=supabase,
            user=user,
        )


def show_saved_plans() -> None:
    """저장된 학습계획 화면을 표시합니다."""

    with content_frame(STANDARD_CONTENT_WIDTH):
        render_saved_plans(
            supabase=supabase,
            user=user,
        )


def show_source_review_material() -> None:
    """원본 기반 AI 복습 자료 화면을 표시합니다."""

    with content_frame(STANDARD_CONTENT_WIDTH):
        render_source_review_material(
            supabase=supabase,
            user=user,
        )


def show_tutor() -> None:
    """단계별 힌트 AI 튜터 화면을 표시합니다."""

    with content_frame(STANDARD_CONTENT_WIDTH):
        render_tutor(
            supabase=supabase,
            user=user,
        )


def show_weekly_review() -> None:
    """주간 학습 회고 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_weekly_review(
            supabase=supabase,
            user=user,
        )


def show_mastery_dashboard() -> None:
    """과목별 숙련도 화면을 표시합니다."""

    with content_frame(STANDARD_CONTENT_WIDTH):
        render_mastery_dashboard(
            supabase=supabase,
            user=user,
        )


def show_gamification() -> None:
    """업적·도전과제 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_gamification_page(
            supabase=supabase,
            user=user,
        )


dashboard_page = st.Page(
    show_dashboard,
    title="오늘 학습",
    icon=":material/home:",
    url_path="today",
    default=True,
)
create_plan_page = st.Page(
    show_create_plan,
    title="계획 만들기",
    icon=":material/add_circle:",
    url_path="create-plan",
)
saved_plans_page = st.Page(
    show_saved_plans,
    title="저장된 계획",
    icon=":material/folder:",
    url_path="saved-plans",
)
source_review_page = st.Page(
    show_source_review_material,
    title="AI 복습 자료 만들기",
    icon=":material/article:",
    url_path="review-material",
)
tutor_page = st.Page(
    show_tutor,
    title="단계별 힌트 AI 튜터",
    icon=":material/psychology:",
    url_path="tutor",
)
weekly_review_page = st.Page(
    show_weekly_review,
    title="주간 학습 회고",
    icon=":material/analytics:",
    url_path="weekly-review",
)
mastery_dashboard_page = st.Page(
    show_mastery_dashboard,
    title="과목별 숙련도",
    icon=":material/monitoring:",
    url_path="mastery",
)
gamification_page = st.Page(
    show_gamification,
    title="업적·도전과제",
    icon=":material/military_tech:",
    url_path="gamification",
)

pages_by_title = {
    "오늘 학습": dashboard_page,
    "계획 만들기": create_plan_page,
    "저장된 계획": saved_plans_page,
    "AI 복습 자료 만들기": source_review_page,
    "단계별 힌트 AI 튜터": tutor_page,
    "과목별 숙련도": mastery_dashboard_page,
    "업적·도전과제": gamification_page,
    "주간 학습 회고": weekly_review_page,
}

selected_page = st.navigation(
    {
        "": [dashboard_page],
        "계획": [create_plan_page, saved_plans_page],
        "AI 도구": [source_review_page, tutor_page],
        "성장": [
            mastery_dashboard_page,
            gamification_page,
            weekly_review_page,
        ],
    },
    position="sidebar",
    expanded=True,
)

pending_navigation = st.session_state.pop(
    WEEKLY_REVIEW_PENDING_NAVIGATION_KEY,
    None,
)
if pending_navigation is None:
    pending_navigation = st.session_state.pop(
        GAMIFICATION_PENDING_NAVIGATION_KEY,
        None,
    )
if pending_navigation in pages_by_title:
    st.switch_page(pages_by_title[pending_navigation])


render_gamification_notifications()


with st.sidebar:
    with st.container(border=True):
        st.caption("로그인 사용자")
        st.markdown(f"### {profile['nickname']}")
        st.caption(
            f"레벨 {profile['level']} · "
            f"총 {profile['total_exp']} EXP · "
            f"연속 학습 {profile['current_streak']}일"
        )

    if st.button(
        "로그아웃",
        key="logout_button",
        icon=":material/logout:",
        width="stretch",
    ):
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
        clear_weekly_review_state(st.session_state)
        clear_gamification_state(st.session_state)
        clear_shop_state(st.session_state)
        clear_test_tools_state(st.session_state)

        clear_auth_session_state()
        st.rerun()

render_sidebar_test_tools(
    supabase=supabase,
    user=user,
)

selected_page.run()
