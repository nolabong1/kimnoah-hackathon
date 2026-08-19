from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import (
    complete_study_task,
    delete_study_plan,
    get_study_plan_tasks,
    get_user_study_plans,
)
from views.completion_feedback import (
    render_completion_feedback,
)
from views.gamification_state import queue_gamification_notifications
from views.quiz_ui import render_quiz_section
from views.review_material_ui import (
    render_review_material_section,
)
from views.spaced_review_ui import (
    get_spaced_review_label,
)
from views.ui_components import (
    MetricItem,
    render_empty_state,
    render_metric_row,
    render_page_header,
)


SAVED_PLAN_SELECT_KEY = "saved_plan_selected_id"
DELETED_PLAN_CLEANUP_KEY = "saved_plan_deleted_plan_id"
DELETE_PLAN_MESSAGE_KEY = "saved_plan_delete_message"
SAVED_DATE_SELECT_PREFIX = "saved_plan_selected_date_"


def get_date_select_key(plan_id: str) -> str:
    """계획별 선택 날짜 위젯의 고유 상태 키를 반환합니다."""

    return f"{SAVED_DATE_SELECT_PREFIX}{plan_id}"


def apply_deleted_plan_state() -> None:
    """삭제 후 rerun에서 선택된 계획과 관련 상태를 정리합니다."""

    deleted_plan_id = st.session_state.pop(
        DELETED_PLAN_CLEANUP_KEY,
        None,
    )

    if deleted_plan_id is None:
        return

    st.session_state.pop(SAVED_PLAN_SELECT_KEY, None)
    st.session_state.pop("pending_future_task_id", None)
    st.session_state.pop(
        "saved_plan_pending_open_date",
        None,
    )

    if st.session_state.get("saved_plan_id") == deleted_plan_id:
        st.session_state.pop("saved_plan_id", None)
        st.session_state["generated_plan_saved"] = False

    for state_key in list(st.session_state.keys()):
        if state_key.startswith(
            f"saved_plan_date_expander_{deleted_plan_id}_"
        ) or state_key == get_date_select_key(deleted_plan_id):
            st.session_state.pop(state_key, None)


@st.dialog("학습계획 삭제")
def show_delete_plan_dialog(
    supabase,
    user_id,
    plan,
) -> None:
    """선택한 학습계획의 영구 삭제를 다시 확인합니다."""

    st.warning(
        "삭제한 학습계획은 복구할 수 없습니다.",
        icon=":material/warning:",
    )
    st.write(f"**{plan['title']}** 계획을 삭제할까요?")
    st.caption(
        "상세 과제, AI 학습자료, 퀴즈와 응시 결과가 "
        "함께 삭제됩니다. 이미 획득한 EXP와 성장 기록은 유지됩니다."
    )

    with st.container(
        horizontal=True,
        horizontal_alignment="right",
    ):
        if st.button(
            "취소",
            key=f"cancel_delete_plan_{plan['id']}",
        ):
            st.rerun()

        if st.button(
            "삭제하기",
            key=f"confirm_delete_plan_{plan['id']}",
            type="primary",
            icon=":material/delete:",
        ):
            try:
                with st.spinner(
                    "학습계획과 연결된 데이터를 삭제하고 있습니다..."
                ):
                    delete_study_plan(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan["id"],
                    )

                st.session_state[DELETED_PLAN_CLEANUP_KEY] = (
                    plan["id"]
                )
                st.session_state[DELETE_PLAN_MESSAGE_KEY] = (
                    f"'{plan['title']}' 학습계획을 삭제했습니다."
                )
                st.rerun()

            except Exception as error:
                st.error(
                    f"학습계획 삭제에 실패했습니다: {error}"
                )


def complete_task_and_rerun(
    supabase,
    task_id,
    scheduled_date,
):
    try:
        with st.spinner(
            "과제 완료를 기록하고 있습니다..."
        ):
            result = complete_study_task(
                supabase=supabase,
                task_id=task_id,
            )

        queue_gamification_notifications(
            st.session_state,
            result.get("gamification"),
        )

        if result["already_completed"]:
            message = "이미 완료된 과제입니다."
        else:
            message = (
                f"과제 완료! "
                f"+{result['task_exp']} EXP"
            )

            if result["daily_bonus_exp"] > 0:
                message += (
                    " · 오늘의 계획 완료 보너스 "
                    f"+{result['daily_bonus_exp']} EXP"
                )

            message += (
                f" · 총 EXP {result['total_exp']}"
            )

        st.session_state.task_completion_feedback = {
            "message": message,
            "daily_bonus_exp": result.get(
                "daily_bonus_exp",
                0,
            ),
        }

        st.session_state.saved_plan_pending_open_date = (
            scheduled_date
        )
    
        st.rerun()

    except Exception as error:
        st.error(
            f"과제 완료 처리에 실패했습니다: {error}"
        )


def get_saved_plan_date_label(
    scheduled_date: str,
    tasks: list[dict],
) -> str:
    """날짜 선택 목록에 완료 현황과 예상 시간을 함께 표시합니다."""

    completed_count = sum(
        task.get("status") == "completed"
        for task in tasks
    )
    total_minutes = sum(
        int(task.get("estimated_minutes", 0))
        for task in tasks
    )
    return (
        f"{scheduled_date} · "
        f"{completed_count}/{len(tasks)} 완료 · "
        f"{total_minutes}분"
    )


def _render_saved_task_card(
    *,
    supabase,
    user_id: str,
    selected_plan: dict,
    task: dict,
    today: str,
) -> None:
    """선택 날짜의 과제 하나와 기존 완료·자료·퀴즈 동작을 표시합니다."""

    task_type_names = {
        "learn": ":material/menu_book: 학습",
        "review": ":material/replay: 복습",
        "quiz": ":material/quiz: 퀴즈",
    }
    task_status_names = {
        "pending": "대기",
        "completed": "완료",
        "skipped": "건너뜀",
    }
    quiz_completion_unlocked = True

    with st.container(border=True):
        task_type = task_type_names[task["task_type"]]
        task_status = task_status_names[task["status"]]
        st.markdown(f"#### {task_type} · {task['title']}")
        st.caption(
            f"예상 {task['estimated_minutes']}분 · {task_status}"
        )
        st.write(task["description"])

        review_label = get_spaced_review_label(task)
        if review_label:
            st.caption(review_label)

        if task["task_type"] in {"learn", "review"}:
            render_review_material_section(
                supabase=supabase,
                user_id=user_id,
                plan_id=selected_plan["id"],
                course_name=selected_plan["course_name"],
                goal=selected_plan["goal"],
                current_level=selected_plan["current_level"],
                task=task,
                widget_scope="saved_plan",
            )
        elif task["task_type"] == "quiz":
            quiz_completion_unlocked = render_quiz_section(
                supabase=supabase,
                user_id=user_id,
                plan_id=selected_plan["id"],
                course_name=selected_plan["course_name"],
                goal=selected_plan["goal"],
                current_level=selected_plan["current_level"],
                task=task,
                widget_scope="saved_plan",
            )

        if task["status"] == "completed":
            st.success(
                "완료된 과제입니다.",
                icon=":material/check_circle:",
            )
            return

        is_future_task = task["scheduled_date"] > today
        pending_future_task_id = st.session_state.get(
            "pending_future_task_id"
        )
        quiz_completion_locked = (
            task["task_type"] == "quiz"
            and not quiz_completion_unlocked
        )

        if quiz_completion_locked:
            if pending_future_task_id == task["id"]:
                st.session_state.pop("pending_future_task_id", None)
            st.button(
                "완료하기",
                key=f"complete_task_{task['id']}",
                disabled=True,
                help="현재 퀴즈의 모든 문항을 맞히면 완료할 수 있습니다.",
            )
            return

        if is_future_task and pending_future_task_id == task["id"]:
            st.warning(
                "아직 예정일 전인 과제입니다. "
                f"예정일은 {task['scheduled_date']}입니다. "
                "그래도 미리 완료할까요?"
            )
            with st.container(horizontal=True):
                if st.button(
                    "그래도 완료하기",
                    key=f"confirm_future_{task['id']}",
                    type="primary",
                    width="stretch",
                ):
                    st.session_state.pop("pending_future_task_id", None)
                    complete_task_and_rerun(
                        supabase=supabase,
                        task_id=task["id"],
                        scheduled_date=task["scheduled_date"],
                    )

                if st.button(
                    "취소",
                    key=f"cancel_future_{task['id']}",
                    width="stretch",
                ):
                    st.session_state.pop("pending_future_task_id", None)
                    st.rerun()
            return

        if st.button(
            "완료하기",
            key=f"complete_task_{task['id']}",
        ):
            if is_future_task:
                st.session_state["saved_plan_pending_open_date"] = (
                    task["scheduled_date"]
                )
                st.session_state["pending_future_task_id"] = task["id"]
                st.rerun()
            else:
                complete_task_and_rerun(
                    supabase=supabase,
                    task_id=task["id"],
                    scheduled_date=task["scheduled_date"],
                )


def render_saved_plans(supabase, user):
    apply_deleted_plan_state()

    render_page_header(
        "저장된 계획",
        "계획별 일정과 과제를 날짜 단위로 확인하고 관리하세요.",
    )

    render_completion_feedback()

    if DELETE_PLAN_MESSAGE_KEY in st.session_state:
        st.success(
            st.session_state.pop(
                DELETE_PLAN_MESSAGE_KEY
            )
        )

    try:
        saved_plans = get_user_study_plans(
            supabase=supabase,
            user_id=user.id,
        )

    except Exception as error:
        st.error(
            f"저장된 학습계획을 불러오지 못했습니다: "
            f"{error}"
        )
        saved_plans = []

    if not saved_plans:
        render_empty_state(
            "저장된 학습계획이 없습니다",
            "계획 만들기에서 새로운 7일 계획을 생성해보세요.",
            icon=":material/folder_open:",
        )
        return

    plan_by_id = {
        saved_plan["id"]: saved_plan
        for saved_plan in saved_plans
    }

    selected_plan_id = st.selectbox(
        "확인할 계획",
        options=list(plan_by_id.keys()),
        format_func=lambda plan_id: (
            f"{plan_by_id[plan_id]['title']} · "
            f"{plan_by_id[plan_id]['start_date']}"
        ),
        key=SAVED_PLAN_SELECT_KEY,
    )

    selected_plan = plan_by_id[selected_plan_id]

    with st.container(border=True):
        st.subheader(selected_plan["title"])
        render_metric_row(
            [
                MetricItem(
                    "과목",
                    selected_plan["course_name"],
                    icon=":material/menu_book:",
                ),
                MetricItem(
                    "시작일",
                    selected_plan["start_date"],
                    icon=":material/event:",
                ),
                MetricItem(
                    "종료일",
                    selected_plan["target_date"],
                    icon=":material/event_available:",
                ),
            ]
        )
        st.write(f"**학습 목표:** {selected_plan['goal']}")

    with st.container(
        horizontal=True,
        horizontal_alignment="right",
    ):
        st.caption("계획 삭제는 별도의 확인 절차를 거칩니다.")
        if st.button(
            "계획 삭제",
            key=f"delete_plan_{selected_plan_id}",
            type="tertiary",
            icon=":material/delete:",
        ):
            show_delete_plan_dialog(
                supabase=supabase,
                user_id=user.id,
                plan=selected_plan,
            )

    try:
        saved_tasks = get_study_plan_tasks(
            supabase=supabase,
            user_id=user.id,
            plan_id=selected_plan_id,
        )

    except Exception as error:
        st.error(
            f"상세 과제를 불러오지 못했습니다: "
            f"{error}"
        )
        saved_tasks = []

    if not saved_tasks:
        render_empty_state(
            "저장된 상세 과제가 없습니다",
            "이 계획에는 표시할 일정이 없습니다.",
            icon=":material/event_busy:",
        )
        return

    tasks_by_date = {}

    for task in saved_tasks:
        scheduled_date = task["scheduled_date"]

        if scheduled_date not in tasks_by_date:
            tasks_by_date[scheduled_date] = []

        tasks_by_date[scheduled_date].append(task)

    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()
    scheduled_dates = sorted(tasks_by_date)
    default_selected_date = (
        today
        if today in tasks_by_date
        else scheduled_dates[0]
    )
    pending_open_date = st.session_state.pop(
        "saved_plan_pending_open_date",
        None,
    )
    date_select_key = get_date_select_key(selected_plan_id)
    if pending_open_date in scheduled_dates:
        st.session_state[date_select_key] = pending_open_date
    elif st.session_state.get(date_select_key) not in scheduled_dates:
        st.session_state[date_select_key] = default_selected_date

    with st.container(border=True):
        st.subheader("학습 일정")
        selected_date = st.selectbox(
            "상세 내용을 확인할 날짜",
            options=scheduled_dates,
            key=date_select_key,
            format_func=lambda scheduled_date: get_saved_plan_date_label(
                scheduled_date,
                tasks_by_date[scheduled_date],
            ),
            label_visibility="collapsed",
            persist_state="session",
        )
        st.caption("선택한 날짜의 과제가 아래에 표시됩니다.")

    selected_tasks = tasks_by_date[selected_date]

    for task in selected_tasks:
        _render_saved_task_card(
            supabase=supabase,
            user_id=str(user.id),
            selected_plan=selected_plan,
            task=task,
            today=today,
        )
