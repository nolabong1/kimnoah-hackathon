from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import (
    complete_study_task,
    get_study_plan_tasks,
    get_user_study_plans,
)
from views.completion_feedback import render_completion_feedback
from views.review_material_ui import (
    render_review_material_section,
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

    today_tasks = []

    try:
        for saved_plan in saved_plans:
            plan_tasks = get_study_plan_tasks(
                supabase=supabase,
                user_id=user.id,
                plan_id=saved_plan["id"],
            )

            for task in plan_tasks:
                if task["scheduled_date"] != today:
                    continue

                task_with_plan = dict(task)
                task_with_plan["plan_title"] = (
                    saved_plan["title"]
                )
                task_with_plan["course_name"] = (
                    saved_plan["course_name"]
                )
                task_with_plan["plan_id"] = (
                    saved_plan["id"]
                )
                task_with_plan["goal"] = (
                    saved_plan["goal"]
                )
                task_with_plan["current_level"] = (
                    saved_plan["current_level"]
                )

                today_tasks.append(task_with_plan)

    except Exception as error:
        st.error(
            f"오늘의 과제를 불러오지 못했습니다: {error}"
        )
        return

    if not today_tasks:
        st.info(
            "오늘 예정된 과제가 없습니다. "
            "새로운 계획을 만들거나 저장된 계획을 확인해보세요."
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
        "오늘의 과제",
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
            f"오늘의 진행률 "
            f"{completed_count}/{total_count}"
        ),
    )

    if completed_count == total_count:
        st.success(
            "오늘의 모든 학습을 완료했습니다! 🎉"
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

            if task["status"] == "completed":
                st.success("완료된 과제입니다. ✅")
                continue

            if st.button(
                "과제 완료하기",
                key=f"dashboard_complete_{task['id']}",
                type="primary",
                use_container_width=True,
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
