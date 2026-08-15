import streamlit as st

from services.study_plan_repository import (
    complete_study_task,
    get_study_plan_tasks,
    get_user_study_plans,
)


def render_saved_plans(supabase, user):
    st.divider()
    st.subheader("저장된 학습계획")

    if "task_completion_message" in st.session_state:
        completion_message = st.session_state.pop(
            "task_completion_message"
        )

        st.toast(
            completion_message,
            icon="🎉",
        )
        st.success(completion_message)

    if st.session_state.pop(
        "daily_completion_celebration",
        False,
    ):
        st.balloons()

    try:
        saved_plans = get_user_study_plans(
            supabase=supabase,
            user_id=user.id,
        )

    except Exception as error:
        st.error(
            f"저장된 학습계획을 불러오지 못했습니다: {error}"
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

    plan_column1, plan_column2, plan_column3 = st.columns(3)

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

    st.write(f"**학습 목표:** {selected_plan['goal']}")

    try:
        saved_tasks = get_study_plan_tasks(
            supabase=supabase,
            user_id=user.id,
            plan_id=selected_plan_id,
        )

    except Exception as error:
        st.error(f"상세 과제를 불러오지 못했습니다: {error}")
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

    first_date = min(tasks_by_date.keys())

    for scheduled_date, daily_tasks in tasks_by_date.items():
        total_minutes = sum(
            task["estimated_minutes"]
            for task in daily_tasks
        )

        with st.expander(
            f"{scheduled_date} · "
            f"과제 {len(daily_tasks)}개 · "
            f"총 {total_minutes}분",
            expanded=scheduled_date == first_date,
        ):
            for task in daily_tasks:
                task_type = task_type_names[task["task_type"]]
                task_status = task_status_names[task["status"]]

                st.markdown(
                    f"**{task_type} · {task['title']}** "
                    f"— {task['estimated_minutes']}분 · "
                    f"{task_status}"
                )
                st.write(task["description"])

                if task["status"] == "completed":
                    st.caption("✅ 완료된 과제입니다.")

                elif st.button(
                    "완료하기",
                    key=f"complete_task_{task['id']}",
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

                        st.session_state.task_completion_message = (
                            message
                        )
                        st.session_state.daily_completion_celebration = (
                            result.get("daily_bonus_exp", 0) > 0
                        )
                        st.rerun()

                    except Exception as error:
                        st.error(
                            f"과제 완료 처리에 실패했습니다: {error}"
                        )