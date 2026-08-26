from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from services.error_reporting import report_exception
from services.shop_repository import (
    get_active_shop_test_session,
    reset_shop_test_session,
    start_shop_test_session,
)
from services.study_plan_repository import (
    complete_study_plan_for_weekly_review_test,
    get_study_plan_tasks,
    get_user_study_plans,
    reset_today_test_progress,
)
from services.test_tools_repository import can_use_test_tools
from views.error_feedback import render_unexpected_error
from views.weekly_review_state import TEST_COMPLETED_PLAN_PENDING_KEY


TEST_TOOLS_STATE_PREFIX = "test_tools_"
TEST_TOOLS_EXPANDER_KEY = "test_tools_sidebar_expander"
RESET_CONFIRM_KEY = "test_tools_reset_confirmation"
RESET_MESSAGE_KEY = "test_tools_reset_message"
PLAN_SELECT_KEY = "test_tools_plan_id"
PLAN_CONFIRM_KEY = "test_tools_confirm_plan_id"
PLAN_RUNNING_KEY = "test_tools_plan_completion_running"
PLAN_MESSAGE_KEY = "test_tools_plan_completion_message"
SHOP_TEST_CONFIRM_KEY = "test_tools_shop_confirmation"
SHOP_TEST_RUNNING_KEY = "test_tools_shop_running"
SHOP_TEST_MESSAGE_KEY = "test_tools_shop_message"
ACCESS_CHECKED_KEY = "test_tools_access_checked"
ACCESS_ALLOWED_KEY = "test_tools_access_allowed"


def clear_test_tools_state(state: MutableMapping[str, Any]) -> None:
    """테스트 도구 전용 세션 상태만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(TEST_TOOLS_STATE_PREFIX):
            state.pop(key, None)


def _is_missing_test_completion_rpc_error(error: Exception) -> bool:
    """계획 완료 테스트 RPC 마이그레이션 미적용 오류인지 판정합니다."""

    error_text = str(error).casefold()
    return "complete_study_plan_for_weekly_review_test" in error_text and any(
        marker in error_text
        for marker in ("pgrst", "schema cache", "could not find", "does not exist")
    )


def _is_missing_shop_test_tools_error(error: Exception) -> bool:
    """상점 테스트 도구 마이그레이션 미적용 오류인지 판정합니다."""

    error_text = str(error).casefold()
    return any(
        marker in error_text
        for marker in (
            "shop_test_sessions",
            "start_shop_test_session",
            "reset_shop_test_session",
            "pgrst202",
            "pgrst205",
            "schema cache",
        )
    )


def _render_reset_tool(supabase) -> None:
    """오늘의 테스트 기록 초기화와 확인 절차를 표시합니다."""

    st.markdown("**오늘 기록 초기화**")
    st.caption(
        "오늘 완료한 과제와 관련 EXP, 퀴즈 응시, 숙련도 변화, "
        "자동 복습 과제를 되돌립니다."
    )

    if st.session_state.get(RESET_CONFIRM_KEY, False):
        st.warning(
            "오늘 실제로 완료 처리한 모든 과제와 관련 학습 기록이 "
            "초기화됩니다. 진행할까요?"
        )
        with st.container(horizontal=True):
            if st.button(
                "초기화 실행",
                key="test_tools_reset_confirm_button",
                type="primary",
                width="stretch",
            ):
                try:
                    with st.spinner("오늘의 테스트 기록을 초기화하고 있습니다..."):
                        reset_result = reset_today_test_progress(
                            supabase=supabase,
                        )

                    st.session_state.pop(RESET_CONFIRM_KEY, None)
                    st.session_state.pop("pending_future_task_id", None)
                    for state_key in list(st.session_state):
                        if "_quiz_attempt_" in str(state_key):
                            st.session_state.pop(state_key, None)

                    removed_attempt_count = reset_result.get(
                        "removed_quiz_attempt_count",
                        0,
                    )
                    removed_mastery_event_count = reset_result.get(
                        "removed_mastery_event_count",
                        0,
                    )
                    removed_auto_review_count = reset_result.get(
                        "removed_auto_review_task_count",
                        0,
                    )
                    st.session_state[RESET_MESSAGE_KEY] = (
                        f"오늘 완료한 과제 {reset_result['reset_task_count']}개와 "
                        f"퀴즈 응시 {removed_attempt_count}회, "
                        f"숙련도 변경 {removed_mastery_event_count}건, "
                        f"자동 복습 과제 {removed_auto_review_count}개, "
                        f"{reset_result['removed_total_exp']} EXP를 초기화했습니다."
                    )
                    st.session_state["saved_plan_pending_open_date"] = str(
                        reset_result["reset_date"]
                    )
                    st.rerun()
                except Exception as error:
                    render_unexpected_error(
                        error,
                        operation="test_tools.reset_today",
                        user_message=(
                            "테스트 초기화에 실패했습니다. 잠시 후 다시 "
                            "시도해주세요."
                        ),
                    )

            if st.button(
                "취소",
                key="test_tools_reset_cancel_button",
                width="stretch",
            ):
                st.session_state.pop(RESET_CONFIRM_KEY, None)
                st.rerun()
        return

    if st.button(
        "오늘 테스트 기록 초기화",
        key="test_tools_reset_button",
        icon=":material/restart_alt:",
        width="stretch",
    ):
        st.session_state[RESET_CONFIRM_KEY] = True
        st.rerun()


def _render_plan_completion_tool(
    *,
    supabase,
    user_id: str,
) -> None:
    """선택한 본인 계획의 미완료 과제를 테스트용으로 완료합니다."""

    st.divider()
    st.markdown("**계획 전체 완료**")
    st.caption(
        "선택한 계획의 미완료 과제를 오늘 일괄 완료합니다. "
        "퀴즈 만점 조건은 이 테스트에서만 우회합니다."
    )

    try:
        plans = get_user_study_plans(
            supabase=supabase,
            user_id=user_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="test_tools.load_plans",
            user_message=(
                "테스트할 학습계획을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not plans:
        st.info("테스트할 저장된 학습계획이 없습니다.")
        return

    plan_by_id = {
        str(plan["id"]): plan
        for plan in plans
    }
    plan_ids = list(plan_by_id)
    if st.session_state.get(PLAN_SELECT_KEY) not in plan_ids:
        st.session_state.pop(PLAN_SELECT_KEY, None)

    selected_plan_id = st.selectbox(
        "테스트 완료할 계획",
        options=plan_ids,
        format_func=lambda plan_id: (
            f"{plan_by_id[plan_id]['title']} · "
            f"{plan_by_id[plan_id]['start_date']}"
        ),
        key=PLAN_SELECT_KEY,
    )

    try:
        selected_tasks = get_study_plan_tasks(
            supabase=supabase,
            user_id=user_id,
            plan_id=selected_plan_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="test_tools.load_plan_tasks",
            user_message=(
                "선택한 계획의 과제를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    incomplete_tasks = [
        task
        for task in selected_tasks
        if task.get("status") != "completed"
    ]
    incomplete_quiz_count = sum(
        task.get("task_type") == "quiz"
        for task in incomplete_tasks
    )

    if not selected_tasks:
        st.warning("이 계획에는 완료 처리할 과제가 없습니다.")
        return
    if not incomplete_tasks:
        st.success("이 계획의 모든 과제가 이미 완료되었습니다.")
        return

    st.caption(
        f"미완료 {len(incomplete_tasks)}개 · "
        f"퀴즈 {incomplete_quiz_count}개 · "
        f"예상 {len(incomplete_tasks) * 10} EXP"
    )

    if st.session_state.get(PLAN_CONFIRM_KEY) != selected_plan_id:
        if st.button(
            "이번 주 계획 완료 처리",
            key=f"test_tools_complete_plan_{selected_plan_id}",
            icon=":material/check_circle:",
            width="stretch",
        ):
            st.session_state[PLAN_CONFIRM_KEY] = selected_plan_id
            st.rerun()
        return

    st.warning(
        "미래 과제와 아직 만점을 받지 않은 퀴즈 과제도 완료됩니다. "
        "과제당 10 EXP와 조건 충족 시 오늘의 20 EXP가 실제로 기록됩니다."
    )
    with st.container(horizontal=True):
        if st.button(
            "완료 실행",
            key=f"test_tools_confirm_plan_{selected_plan_id}",
            type="primary",
            disabled=st.session_state.get(PLAN_RUNNING_KEY, False),
            width="stretch",
        ):
            if st.session_state.get(PLAN_RUNNING_KEY, False):
                st.warning("이미 테스트 완료를 처리하고 있습니다.")
            else:
                st.session_state[PLAN_RUNNING_KEY] = True
                try:
                    with st.spinner("계획의 과제와 보상을 완료 처리하고 있습니다..."):
                        result = complete_study_plan_for_weekly_review_test(
                            supabase=supabase,
                            plan_id=selected_plan_id,
                        )

                    if result["already_completed"]:
                        message = "선택한 계획은 이미 모두 완료되어 있습니다."
                    else:
                        message = (
                            f"과제 {result['completed_task_count']}개를 완료하고 "
                            f"{result['task_exp']} EXP를 지급했습니다."
                        )
                        if result["daily_bonus_exp"] > 0:
                            message += (
                                " 오늘의 계획 완료 보너스 "
                                f"{result['daily_bonus_exp']} EXP도 지급했습니다."
                            )

                    st.session_state[PLAN_MESSAGE_KEY] = message
                    st.session_state[TEST_COMPLETED_PLAN_PENDING_KEY] = (
                        selected_plan_id
                    )
                    st.session_state.pop(PLAN_CONFIRM_KEY, None)
                    st.rerun()
                except Exception as error:
                    if _is_missing_test_completion_rpc_error(error):
                        user_message = (
                            "테스트 완료 RPC가 아직 없습니다. Supabase SQL "
                            "Editor에서 supabase_weekly_review_test_completion.sql을 "
                            "먼저 실행해주세요."
                        )
                    else:
                        user_message = (
                            "학습계획 테스트 완료 처리에 실패했습니다. "
                            "연결 상태를 확인한 뒤 다시 시도해주세요."
                        )
                    render_unexpected_error(
                        error,
                        operation="test_tools.complete_plan",
                        user_message=user_message,
                    )
                finally:
                    st.session_state[PLAN_RUNNING_KEY] = False

        if st.button(
            "취소",
            key=f"test_tools_cancel_plan_{selected_plan_id}",
            width="stretch",
        ):
            st.session_state.pop(PLAN_CONFIRM_KEY, None)
            st.rerun()


def _render_shop_test_tool(
    *,
    supabase,
    user_id: str,
) -> None:
    """기존 상태를 보존하는 상점 테스트 세션 제어를 표시합니다."""

    st.divider()
    st.markdown("**상점 테스트 세션**")
    st.caption(
        "테스트 코인 1,200개로 실제 구매·장착 흐름을 확인합니다. "
        "초기화하면 테스트 구매만 제거하고 시작 전 학습방을 복원합니다."
    )

    try:
        active_session = get_active_shop_test_session(
            supabase=supabase,
            user_id=user_id,
        )
    except Exception as error:
        if _is_missing_shop_test_tools_error(error):
            user_message = (
                "상점 테스트 도구를 사용하려면 Supabase SQL Editor에서 "
                "supabase_shop_test_tools.sql을 먼저 실행해주세요."
            )
        else:
            user_message = (
                "상점 테스트 상태를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            )
        render_unexpected_error(
            error,
            operation="test_tools.load_shop_session",
            user_message=user_message,
        )
        return

    confirmation = st.session_state.get(SHOP_TEST_CONFIRM_KEY)
    if active_session is None and confirmation == "reset":
        st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
        confirmation = None
    elif active_session is not None and confirmation == "start":
        st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
        confirmation = None

    if active_session is None:
        st.info("현재 진행 중인 상점 테스트 세션이 없습니다.")
        if confirmation != "start":
            if st.button(
                "상점 테스트 시작",
                key="test_tools_shop_start_button",
                icon=":material/toll:",
                width="stretch",
            ):
                st.session_state[SHOP_TEST_CONFIRM_KEY] = "start"
                st.rerun()
            return

        st.warning(
            "현재 인벤토리와 학습방을 보존한 뒤 테스트 코인 1,200개를 "
            "지급합니다. 테스트 종료 후 반드시 이 도구에서 초기화해주세요."
        )
        with st.container(horizontal=True):
            if st.button(
                "테스트 시작 실행",
                key="test_tools_shop_start_confirm_button",
                type="primary",
                disabled=st.session_state.get(SHOP_TEST_RUNNING_KEY, False),
                width="stretch",
            ):
                st.session_state[SHOP_TEST_RUNNING_KEY] = True
                try:
                    with st.spinner("상점 테스트 상태를 준비하고 있습니다..."):
                        result = start_shop_test_session(supabase)
                    if result["already_active"]:
                        message = "이미 진행 중인 상점 테스트 세션을 불러왔습니다."
                    else:
                        message = (
                            f"테스트 코인 {result['credit_amount']}개를 지급했습니다. "
                            f"현재 잔액은 {result['balance']}개입니다."
                        )
                    st.session_state[SHOP_TEST_MESSAGE_KEY] = message
                    st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
                    st.rerun()
                except Exception as error:
                    if _is_missing_shop_test_tools_error(error):
                        user_message = (
                            "Supabase SQL Editor에서 "
                            "supabase_shop_test_tools.sql을 먼저 실행해주세요."
                        )
                    else:
                        user_message = (
                            "상점 테스트 세션을 시작하지 못했습니다. 잠시 "
                            "후 다시 시도해주세요."
                        )
                    render_unexpected_error(
                        error,
                        operation="test_tools.start_shop_session",
                        user_message=user_message,
                    )
                finally:
                    st.session_state.pop(SHOP_TEST_RUNNING_KEY, None)

            if st.button(
                "취소",
                key="test_tools_shop_start_cancel_button",
                width="stretch",
            ):
                st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
                st.rerun()
        return

    st.warning(
        f"상점 테스트가 진행 중입니다. 지급 코인 "
        f"{active_session['credit_amount']}개 · "
        f"시작 {str(active_session['started_at'])[:16]}"
    )
    st.caption(
        "상점과 학습방 화면에서 구매·장착을 시험한 뒤 여기에서 "
        "테스트 상태를 초기화하세요. 정상 학습으로 받은 코인은 유지됩니다."
    )

    if confirmation != "reset":
        if st.button(
            "상점 테스트 초기화",
            key="test_tools_shop_reset_button",
            icon=":material/restore:",
            width="stretch",
        ):
            st.session_state[SHOP_TEST_CONFIRM_KEY] = "reset"
            st.rerun()
        return

    st.warning(
        "테스트 중 구매한 아이템을 제거하고 구매 코인을 환급한 뒤, "
        "지급했던 테스트 코인을 회수하고 이전 학습방을 복원합니다."
    )
    with st.container(horizontal=True):
        if st.button(
            "테스트 초기화 실행",
            key="test_tools_shop_reset_confirm_button",
            type="primary",
            disabled=st.session_state.get(SHOP_TEST_RUNNING_KEY, False),
            width="stretch",
        ):
            st.session_state[SHOP_TEST_RUNNING_KEY] = True
            try:
                with st.spinner("상점 테스트 구매와 학습방을 복원하고 있습니다..."):
                    result = reset_shop_test_session(
                        supabase=supabase,
                        session_id=str(active_session["id"]),
                    )
                st.session_state[SHOP_TEST_MESSAGE_KEY] = (
                    f"테스트 구매 {result['removed_inventory_count']}개와 "
                    f"{result['refunded_coin_amount']} 코인을 정리했습니다. "
                    f"복원 후 잔액은 {result['balance']}개입니다."
                )
                st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
                st.rerun()
            except Exception as error:
                if _is_missing_shop_test_tools_error(error):
                    user_message = (
                        "상점 테스트 초기화 RPC가 없습니다. "
                        "Supabase 마이그레이션을 확인해주세요."
                    )
                else:
                    user_message = (
                        "상점 테스트 상태를 안전하게 초기화하지 못했습니다. "
                        "잠시 후 다시 시도해주세요."
                    )
                render_unexpected_error(
                    error,
                    operation="test_tools.reset_shop_session",
                    user_message=user_message,
                )
            finally:
                st.session_state.pop(SHOP_TEST_RUNNING_KEY, None)

        if st.button(
            "취소",
            key="test_tools_shop_reset_cancel_button",
            width="stretch",
        ):
            st.session_state.pop(SHOP_TEST_CONFIRM_KEY, None)
            st.rerun()


def render_sidebar_test_tools(
    *,
    supabase,
    user,
) -> None:
    """인증 사용자의 개발용 테스트 도구를 사이드바에 표시합니다."""

    if not st.session_state.get(ACCESS_CHECKED_KEY, False):
        try:
            access_allowed = can_use_test_tools(supabase)
        except Exception as error:
            report_exception("test_tools.check_access", error)
            access_allowed = False
        st.session_state[ACCESS_ALLOWED_KEY] = access_allowed
        st.session_state[ACCESS_CHECKED_KEY] = True

    if not st.session_state.get(ACCESS_ALLOWED_KEY, False):
        return

    with st.sidebar:
        tools_expander = st.expander(
            "테스트 도구",
            key=TEST_TOOLS_EXPANDER_KEY,
            icon=":material/science:",
            on_change="rerun",
        )
        if not tools_expander.open:
            return

        with tools_expander:
            if RESET_MESSAGE_KEY in st.session_state:
                st.success(st.session_state.pop(RESET_MESSAGE_KEY))
            if PLAN_MESSAGE_KEY in st.session_state:
                st.success(st.session_state.pop(PLAN_MESSAGE_KEY))
            if SHOP_TEST_MESSAGE_KEY in st.session_state:
                st.success(st.session_state.pop(SHOP_TEST_MESSAGE_KEY))

            _render_reset_tool(supabase)
            _render_plan_completion_tool(
                supabase=supabase,
                user_id=str(user.id),
            )
            _render_shop_test_tool(
                supabase=supabase,
                user_id=str(user.id),
            )
