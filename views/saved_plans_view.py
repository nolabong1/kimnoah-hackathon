from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import (
    complete_study_task,
    get_study_plan_tasks,
    get_user_study_plans,
    reset_today_test_progress,
)
from views.completion_feedback import (
    render_completion_feedback,
)
from views.review_material_ui import (
    render_review_material_section,
)


def get_date_expander_key(
    plan_id,
    scheduled_date,
):
    """날짜별 expander의 고유 상태 키를 반환합니다."""

    return (
        f"saved_plan_date_expander_"
        f"{plan_id}_{scheduled_date}"
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


def render_saved_plans(supabase, user):
    st.divider()
    st.subheader("저장된 학습계획")

    render_completion_feedback()

    if "test_reset_message" in st.session_state:
        st.success(
            st.session_state.pop(
                "test_reset_message"
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
        st.info("아직 저장된 학습계획이 없습니다.")
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
    )

    selected_plan = plan_by_id[selected_plan_id]

    plan_column1, plan_column2, plan_column3 = (
        st.columns(3)
    )

    plan_column1.metric(
        "과목",
        selected_plan["course_name"],
    )
    plan_column2.metric(
        "시작일",
        selected_plan["start_date"],
    )
    plan_column3.metric(
        "종료일",
        selected_plan["target_date"],
    )

    st.write(
        f"**학습 목표:** {selected_plan['goal']}"
    )

    with st.expander("🧪 테스트 도구"):
        st.caption(
            "개발 중 보상과 완료 기능을 반복해서 "
            "확인하기 위한 기능입니다."
        )

        if st.session_state.get(
            "test_reset_confirmation",
            False,
        ):
            st.warning(
                "오늘 실제로 완료 처리한 모든 과제와 "
                "해당 EXP가 초기화됩니다. 진행할까요?"
            )

            confirm_column, cancel_column = (
                st.columns(2)
            )

            if confirm_column.button(
                "초기화 실행",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner(
                        "오늘의 테스트 기록을 "
                        "초기화하고 있습니다..."
                    ):
                        reset_result = (
                            reset_today_test_progress(
                                supabase=supabase,
                            )
                        )

                    st.session_state.pop(
                        "test_reset_confirmation",
                        None,
                    )
                    st.session_state.pop(
                        "pending_future_task_id",
                        None,
                    )

                    st.session_state.test_reset_message = (
                        f"오늘 완료한 과제 "
                        f"{reset_result['reset_task_count']}개와 "
                        f"{reset_result['removed_total_exp']} EXP를 "
                        "초기화했습니다."
                    )

                    st.session_state.saved_plan_pending_open_date = (
                        str(reset_result["reset_date"])
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        f"테스트 초기화에 실패했습니다: "
                        f"{error}"
                    )

            if cancel_column.button(
                "취소",
                use_container_width=True,
            ):
                st.session_state.pop(
                    "test_reset_confirmation",
                    None,
                )
                st.rerun()

        elif st.button(
            "오늘 테스트 기록 초기화",
            use_container_width=True,
        ):
            st.session_state.test_reset_confirmation = (
                True
            )
            st.rerun()

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
        st.info("저장된 상세 과제가 없습니다.")
        return

    tasks_by_date = {}

    for task in saved_tasks:
        scheduled_date = task["scheduled_date"]

        if scheduled_date not in tasks_by_date:
            tasks_by_date[scheduled_date] = []

        tasks_by_date[scheduled_date].append(task)

    task_type_names = {
        "learn": "📘 학습",
        "review": "🔁 복습",
        "quiz": "📝 퀴즈",
    }

    task_status_names = {
        "pending": "대기",
        "completed": "완료",
        "skipped": "건너뜀",
    }

    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()

    first_date = min(tasks_by_date.keys())

    if today in tasks_by_date:
        default_open_date = today
    else:
        default_open_date = first_date

    pending_open_date = st.session_state.pop(
        "saved_plan_pending_open_date",
        None,
    )

    for task_date in tasks_by_date:
        expander_key = get_date_expander_key(
            plan_id=selected_plan_id,
            scheduled_date=task_date,
        )

        if pending_open_date is not None:
            st.session_state[expander_key] = (
                task_date == pending_open_date
            )

        elif expander_key not in st.session_state:
            st.session_state[expander_key] = (
                task_date == default_open_date
            )

    for scheduled_date, daily_tasks in (
        tasks_by_date.items()
    ):
        total_minutes = sum(
            task["estimated_minutes"]
            for task in daily_tasks
        )

        expander_key = get_date_expander_key(
            plan_id=selected_plan_id,
            scheduled_date=scheduled_date,
        )

        with st.expander(
            f"{scheduled_date} · "
            f"과제 {len(daily_tasks)}개 · "
            f"총 {total_minutes}분",
            key=expander_key,
            on_change="rerun",
        ):
            # 기존의 for task in daily_tasks 이하 코드는
            # 이 위치에 그대로 유지
            for task in daily_tasks:
                task_type = task_type_names[
                    task["task_type"]
                ]
                task_status = task_status_names[
                    task["status"]
                ]

                st.markdown(
                    f"**{task_type} · {task['title']}** "
                    f"— {task['estimated_minutes']}분 · "
                    f"{task_status}"
                )
                st.write(task["description"])

                if task["task_type"] in {
                    "learn",
                    "review",
                }:
                    render_review_material_section(
                        supabase=supabase,
                        user_id=user.id,
                        plan_id=selected_plan["id"],
                        course_name=selected_plan[
                            "course_name"
                        ],
                        goal=selected_plan["goal"],
                        current_level=selected_plan[
                            "current_level"
                        ],
                        task=task,
                        widget_scope="saved_plan",
                    )

                if task["status"] == "completed":
                    st.caption(
                        "✅ 완료된 과제입니다."
                    )
                    continue

                is_future_task = (
                    task["scheduled_date"] > today
                )
                pending_future_task_id = (
                    st.session_state.get(
                        "pending_future_task_id"
                    )
                )

                if (
                    is_future_task
                    and pending_future_task_id
                    == task["id"]
                ):
                    st.warning(
                        "아직 예정일 전인 과제입니다. "
                        f"예정일은 "
                        f"{task['scheduled_date']}입니다. "
                        "그래도 미리 완료할까요?"
                    )

                    confirm_column, cancel_column = (
                        st.columns(2)
                    )

                    if confirm_column.button(
                        "그래도 완료하기",
                        key=(
                            f"confirm_future_"
                            f"{task['id']}"
                        ),
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.pop(
                            "pending_future_task_id",
                            None,
                        )

                        complete_task_and_rerun(
                            supabase=supabase,
                            task_id=task["id"],
                            scheduled_date=task["scheduled_date"],
                        )

                    if cancel_column.button(
                        "취소",
                        key=(
                            f"cancel_future_"
                            f"{task['id']}"
                        ),
                        use_container_width=True,
                    ):
                        st.session_state.pop(
                            "pending_future_task_id",
                            None,
                        )
                        st.rerun()

                    continue

                if st.button(
                    "완료하기",
                    key=(
                        f"complete_task_{task['id']}"
                    ),
                ):
                    if is_future_task:
                        st.session_state.saved_plan_pending_open_date = (
                            task["scheduled_date"]
                        )
                        st.session_state[
                            "pending_future_task_id"
                        ] = task["id"]
                        st.rerun()

                    else:
                        complete_task_and_rerun(
                            supabase=supabase,
                            task_id=task["id"],
                            scheduled_date=task["scheduled_date"],
                        )
