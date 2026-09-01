import streamlit as st

from services.auth_service import (
    sign_in,
    sign_out,
    sign_up,
)
from services.supabase_client import get_supabase_client

from views.auth_session_storage import (
    activate_auth_response,
    clear_auth_session_state,
    initialize_auth_session,
)
from views.saved_plans_view import (
    PENDING_NAVIGATION_KEY as SAVED_PLANS_PENDING_NAVIGATION_KEY,
    render_saved_plans,
)
from views.create_plan_view import render_create_plan
from views.dashboard_view import render_dashboard
from views.error_feedback import render_unexpected_error
from views.gamification_state import (
    PENDING_NAVIGATION_KEY as GAMIFICATION_PENDING_NAVIGATION_KEY,
    clear_gamification_state,
)
from views.gamification_view import (
    render_gamification_notifications,
    render_gamification_page,
)
from views.help_view import render_help_dialog
from views.interaction_feedback import render_interaction_feedback
from views.interaction_state import clear_interaction_state
from views.mastery_dashboard_view import render_mastery_dashboard
from views.learning_performance_view import render_learning_performance
from views.learning_context_state import (
    PENDING_NAVIGATION_KEY as LEARNING_CONTEXT_PENDING_NAVIGATION_KEY,
    clear_learning_context,
)
from views.shop_pages_view import (
    SHOP_HUB_SECTION_COLLECTION,
    SHOP_HUB_SECTION_KEY,
    SHOP_HUB_SECTION_ROOM,
    render_shop_page,
    render_study_room_page,
)
from views.shop_state import clear_shop_state
from views.profile_state import clear_profile_state, get_profile_snapshot
from views.source_review_material_view import (
    SOURCE_REVIEW_SESSION_KEYS,
    render_source_review_material,
)
from views.tutor_state import clear_tutor_state
from views.tutor_view import render_tutor
from views.test_tools_view import (
    build_streak_preview_profile,
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


def _logout_current_user(supabase) -> None:
    """로그아웃과 사용자별 화면 상태 정리를 다음 rerun 전에 수행합니다."""

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
    clear_learning_context(st.session_state)
    clear_weekly_review_state(st.session_state)
    clear_gamification_state(st.session_state)
    clear_interaction_state(st.session_state)
    clear_shop_state(st.session_state)
    clear_test_tools_state(st.session_state)
    clear_profile_state(st.session_state)
    clear_auth_session_state()


def _empty_auth_page() -> None:
    """비인증 상태에서 숨김 내비게이션이 사용할 빈 페이지입니다."""


st.set_page_config(
    page_title="AI 학습 코치",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

supabase = get_supabase_client()

if st.session_state.get("auth_user") is None:
    st.navigation(
        [st.Page(_empty_auth_page, title="로그인")],
        position="hidden",
    )

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
                        render_unexpected_error(
                            error,
                            operation="auth.sign_in",
                            user_message=(
                                "로그인에 실패했습니다. 이메일과 비밀번호를 "
                                "확인한 뒤 다시 시도해주세요."
                            ),
                        )

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
                            render_unexpected_error(
                                error,
                                operation="auth.sign_up",
                                user_message=(
                                    "회원가입에 실패했습니다. 입력 내용과 연결 "
                                    "상태를 확인한 뒤 다시 시도해주세요."
                                ),
                            )

    st.stop()


# 로그인한 사용자의 프로필 조회
user = st.session_state.auth_user

try:
    stored_profile = get_profile_snapshot(
        client=supabase,
        user_id=str(user.id),
        state=st.session_state,
    )
except Exception as error:
    render_unexpected_error(
        error,
        operation="profile.load",
        user_message=(
            "프로필을 불러오지 못했습니다. 잠시 후 새로고침해주세요."
        ),
    )
    st.stop()

profile = build_streak_preview_profile(
    stored_profile,
    st.session_state,
)


def show_dashboard() -> None:
    """오늘 학습 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_dashboard(
            supabase=supabase,
            user=user,
            profile=profile,
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


def show_learning_performance() -> None:
    """계획별 학습 성과 리포트 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_learning_performance(
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


def show_shop() -> None:
    """코인 상점 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_shop_page(supabase=supabase, user=user)


def show_study_room() -> None:
    """학습방과 보유 현황이 포함된 컬렉션 통합 화면을 표시합니다."""

    with content_frame(DASHBOARD_CONTENT_WIDTH):
        render_study_room_page(
            supabase=supabase,
            user=user,
            profile=profile,
        )


def show_inventory_legacy() -> None:
    """기존 내 아이템 주소를 통합 페이지의 컬렉션으로 연결합니다."""

    st.session_state[SHOP_HUB_SECTION_KEY] = SHOP_HUB_SECTION_COLLECTION
    st.switch_page(study_room_page)


def show_collection_legacy() -> None:
    """기존 컬렉션 주소를 통합 페이지의 해당 영역으로 연결합니다."""

    st.session_state[SHOP_HUB_SECTION_KEY] = SHOP_HUB_SECTION_COLLECTION
    st.switch_page(study_room_page)


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
learning_performance_page = st.Page(
    show_learning_performance,
    title="학습 성과 리포트",
    icon=":material/insights:",
    url_path="learning-performance",
)
gamification_page = st.Page(
    show_gamification,
    title="업적·도전과제",
    icon=":material/military_tech:",
    url_path="gamification",
)
shop_page = st.Page(
    show_shop,
    title="상점",
    icon=":material/storefront:",
    url_path="shop",
)
study_room_page = st.Page(
    show_study_room,
    title="내 학습방",
    icon=":material/chair:",
    url_path="study-room",
)
legacy_inventory_page = st.Page(
    show_inventory_legacy,
    title="내 아이템",
    icon=":material/inventory_2:",
    url_path="inventory",
    visibility="hidden",
)
legacy_collection_page = st.Page(
    show_collection_legacy,
    title="컬렉션",
    icon=":material/collections_bookmark:",
    url_path="collection",
    visibility="hidden",
)

pages_by_title = {
    "오늘 학습": dashboard_page,
    "계획 만들기": create_plan_page,
    "저장된 계획": saved_plans_page,
    "AI 복습 자료 만들기": source_review_page,
    "단계별 힌트 AI 튜터": tutor_page,
    "과목별 숙련도": mastery_dashboard_page,
    "학습 성과 리포트": learning_performance_page,
    "업적·도전과제": gamification_page,
    "주간 학습 회고": weekly_review_page,
    "상점": shop_page,
    "학습방": study_room_page,
    "내 학습방": study_room_page,
    "내 아이템": study_room_page,
    "컬렉션": study_room_page,
}

selected_page = st.navigation(
    {
        "학습하기": [
            dashboard_page,
            saved_plans_page,
            create_plan_page,
        ],
        "AI로 도움받기": [tutor_page, source_review_page],
        "성장 확인하기": [
            learning_performance_page,
            mastery_dashboard_page,
            weekly_review_page,
            gamification_page,
        ],
        "학습방 꾸미기": [
            study_room_page,
            shop_page,
            legacy_inventory_page,
            legacy_collection_page,
        ],
    },
    position="sidebar",
    expanded=True,
)

pending_navigation = st.session_state.pop(
    LEARNING_CONTEXT_PENDING_NAVIGATION_KEY,
    None,
)
if pending_navigation is None:
    pending_navigation = st.session_state.pop(
        WEEKLY_REVIEW_PENDING_NAVIGATION_KEY,
        None,
    )
if pending_navigation is None:
    pending_navigation = st.session_state.pop(
        GAMIFICATION_PENDING_NAVIGATION_KEY,
        None,
    )
if pending_navigation is None:
    pending_navigation = st.session_state.pop(
        SAVED_PLANS_PENDING_NAVIGATION_KEY,
        None,
    )
shop_hub_section_by_navigation = {
    "학습방": SHOP_HUB_SECTION_ROOM,
    "내 학습방": SHOP_HUB_SECTION_ROOM,
    "내 아이템": SHOP_HUB_SECTION_COLLECTION,
    "컬렉션": SHOP_HUB_SECTION_COLLECTION,
}
if pending_navigation in shop_hub_section_by_navigation:
    st.session_state[SHOP_HUB_SECTION_KEY] = (
        shop_hub_section_by_navigation[pending_navigation]
    )
if pending_navigation in pages_by_title:
    st.switch_page(pages_by_title[pending_navigation])


gamification_notifications = render_gamification_notifications()
render_interaction_feedback(gamification_notifications)


with st.sidebar:
    st.caption("처음 방문하셨나요?")
    if st.button(
        "빠른 사용 안내",
        key="open_help_dialog_button",
        type="primary",
        icon=":material/help:",
        width="stretch",
        help="AI 학습 코치의 기본 사용 순서와 주요 기능을 확인합니다.",
    ):
        render_help_dialog()

    with st.container(border=True):
        st.caption("로그인 사용자")
        st.markdown(f"### {profile['nickname']}")
        st.caption(
            f"레벨 {profile['level']} · "
            f"총 {profile['total_exp']} EXP · "
            f"연속 학습 {profile['current_streak']}일"
        )

    st.button(
        "로그아웃",
        key="logout_button",
        icon=":material/logout:",
        width="stretch",
        on_click=_logout_current_user,
        args=(supabase,),
    )

render_sidebar_test_tools(
    supabase=supabase,
    user=user,
    profile=stored_profile,
)

selected_page.run()
