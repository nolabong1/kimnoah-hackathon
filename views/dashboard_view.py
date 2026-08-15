from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import (
    complete_study_task,
    get_study_plan_tasks,
    get_user_study_plans,
)
from views.completion_feedback import render_completion_feedback
from views.quiz_ui import render_quiz_section
from views.review_material_ui import (
    render_review_material_section,
)


DASHBOARD_PLAN_SELECT_KEY = "dashboard_selected_plan_id"


def get_dashboard_plan_label(plan: dict) -> str:
    """오늘 학습 계획 선택지에 표시할 라벨을 만듭니다."""

    return (
        f"{plan['title']} · {plan['course_name']} · "
        f"{plan['start_date']}"
    )


def render_dashboard(supabase, user):
    st.subheader("오늘의 학습")
    st.caption(
        "오늘 해야 할 과제와 현재 진행 상황을 확인하세요."
    )

    render_completion_feedback()

    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()

    try:
        saved_plans = get_user_study_plans(
            supabase=supabase,
            user_id=user.id,
        )

    except Exception as error:
        st.error(
            f"학습계획을 불러오지 못했습니다: {error}"
        )
        return

    if not saved_plans:
        st.info(
            "저장된 학습계획이 없습니다. "
            "먼저 새로운 계획을 만들어 저장해보세요."
        )
        return

    plan_by_id = {
        plan["id"]: plan
        for plan in saved_plans
    }
    plan_ids = list(plan_by_id)

    if st.session_state.get(
        DASHBOARD_PLAN_SELECT_KEY
    ) not in plan_by_id:
        st.session_state[DASHBOARD_PLAN_SELECT_KEY] = (
            plan_ids[0]
        )

    selected_plan_id = st.selectbox(
        "오늘 학습에 표시할 계획",
        options=plan_ids,
        key=DASHBOARD_PLAN_SELECT_KEY,
        format_func=lambda plan_id: get_dashboard_plan_label(
            plan_by_id[plan_id]
        ),
        help="선택한 계획에 예정된 오늘 과제만 표시합니다.",
        persist_state="session",
    )
    selected_plan = plan_by_id[selected_plan_id]

    st.caption(
        "선택한 계획의 오늘 과제와 진행률을 표시합니다."
    )

    try:
        plan_tasks = get_study_plan_tasks(
            supabase=supabase,
            user_id=user.id,
            plan_id=selected_plan_id,
        )

    except Exception as error:
        st.error(
            f"오늘의 과제를 불러오지 못했습니다: {error}"
        )
        return

    today_tasks = []

    for task in plan_tasks:
        if task["scheduled_date"] != today:
            continue

        task_with_plan = dict(task)
        task_with_plan["plan_title"] = (
            selected_plan["title"]
        )
        task_with_plan["course_name"] = (
            selected_plan["course_name"]
        )
        task_with_plan["plan_id"] = selected_plan_id
        task_with_plan["goal"] = selected_plan["goal"]
        task_with_plan["current_level"] = (
            selected_plan["current_level"]
        )

        today_tasks.append(task_with_plan)

    if not today_tasks:
        st.info(
            "선택한 계획에는 오늘 예정된 과제가 없습니다. "
            "다른 계획을 선택하거나 저장된 계획을 확인해보세요."
        )
        return

    completed_count = sum(
        task["status"] == "completed"
        for task in today_tasks
    )
    total_count = len(today_tasks)
    remaining_count = total_count - completed_count
    total_minutes = sum(
        task["estimated_minutes"]
        for task in today_tasks
    )

    metric_column1, metric_column2, metric_column3 = (
        st.columns(3)
    )

    metric_column1.metric(
        "이 계획의 오늘 과제",
        f"{total_count}개",
    )
    metric_column2.metric(
        "남은 과제",
        f"{remaining_count}개",
    )
    metric_column3.metric(
        "예상 학습시간",
        f"{total_minutes}분",
    )

    progress = completed_count / total_count

    st.progress(
        progress,
        text=(
            f"이 계획의 오늘 진행률 "
            f"{completed_count}/{total_count}"
        ),
    )

    if completed_count == total_count:
        st.success(
            "선택한 계획의 오늘 학습을 모두 완료했습니다! 🎉"
        )
    else:
        st.write(
            f"오늘 완료까지 **{remaining_count}개** 남았습니다."
        )

    st.divider()

    task_type_names = {
        "learn": "📘 학습",
        "review": "🔁 복습",
        "quiz": "📝 퀴즈",
    }

    for task in today_tasks:
        task_type = task_type_names.get(
            task["task_type"],
            "📌 과제",
        )

        with st.container(border=True):
            quiz_completion_unlocked = True

            st.caption(
                f"{task['course_name']} · "
                f"{task['plan_title']}"
            )

            st.markdown(
                f"### {task_type} · {task['title']}"
            )

            st.write(task["description"])
            st.caption(
                f"예상 학습시간: "
                f"{task['estimated_minutes']}분"
            )

            if task["task_type"] in {
                "learn",
                "review",
            }:
                render_review_material_section(
                    supabase=supabase,
                    user_id=user.id,
                    plan_id=task["plan_id"],
                    course_name=task["course_name"],
                    goal=task["goal"],
                    current_level=task["current_level"],
                    task=task,
                    widget_scope="dashboard",
                )

            elif task["task_type"] == "quiz":
                quiz_completion_unlocked = render_quiz_section(
                    supabase=supabase,
                    user_id=user.id,
                    plan_id=task["plan_id"],
                    course_name=task["course_name"],
                    goal=task["goal"],
                    current_level=task["current_level"],
                    task=task,
                    widget_scope="dashboard",
                )

            if task["status"] == "completed":
                st.success("완료된 과제입니다. ✅")
                continue

            quiz_completion_locked = (
                task["task_type"] == "quiz"
                and not quiz_completion_unlocked
            )

            if st.button(
                "과제 완료하기",
                key=f"dashboard_complete_{task['id']}",
                type="primary",
                width="stretch",
                disabled=quiz_completion_locked,
                help=(
                    "현재 퀴즈의 모든 문항을 맞히면 "
                    "완료할 수 있습니다."
                    if quiz_completion_locked
                    else None
                ),
            ):
                try:
                    with st.spinner(
                        "과제 완료를 기록하고 있습니다..."
                    ):
                        result = complete_study_task(
                            supabase=supabase,
                            task_id=task["id"],
                        )

                    if result["already_completed"]:
                        message = (
                            "이미 완료된 과제입니다."
                        )
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
                            f" · 총 EXP "
                            f"{result['total_exp']}"
                        )

                    st.session_state.task_completion_feedback = {
                        "message": message,
                        "daily_bonus_exp": result.get(
                            "daily_bonus_exp",
                            0,
                        ),
                    }
                    st.rerun()

                except Exception as error:
                    st.error(
                        f"과제 완료 처리에 실패했습니다: "
                        f"{error}"
                    )
