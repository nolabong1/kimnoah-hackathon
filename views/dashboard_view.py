from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.concept_mastery_repository import (
    get_course_concept_masteries,
)
from services.concept_service import normalize_course_key
from services.study_plan_repository import (
    complete_study_task,
    get_study_plan_tasks,
    get_user_study_plans,
)
from views.completion_feedback import render_completion_feedback
from views.gamification_state import queue_gamification_notifications
from views.gamification_view import (
    render_gamification_dashboard_summary,
)
from views.quiz_ui import render_quiz_section
from views.review_material_ui import (
    render_review_material_section,
)
from views.spaced_review_ui import (
    get_spaced_review_label,
)


DASHBOARD_PLAN_SELECT_KEY = "dashboard_selected_plan_id"
DASHBOARD_TASK_SELECT_KEY = "dashboard_selected_task_id"


def get_dashboard_plan_label(plan: dict) -> str:
    """오늘 학습 계획 선택지에 표시할 라벨을 만듭니다."""

    return (
        f"{plan['title']} · {plan['course_name']} · "
        f"{plan['start_date']}"
    )


def get_dashboard_task_label(task: dict) -> str:
    """오늘 과제 선택 목록에 상태와 유형을 간결하게 표시합니다."""

    task_type_names = {
        "learn": "학습",
        "review": "복습",
        "quiz": "퀴즈",
    }
    status_icon = "✓" if task["status"] == "completed" else "○"
    task_type = task_type_names.get(task["task_type"], "과제")
    return (
        f"{status_icon} {task_type} · {task['title']} "
        f"({task['estimated_minutes']}분)"
    )


def _get_next_auto_review_tasks(
    plan_tasks: list[dict],
    today: str,
) -> list[dict]:
    """오늘 또는 가장 가까운 날짜의 미완료 자동 복습을 반환합니다."""

    upcoming_tasks = [
        task
        for task in plan_tasks
        if task.get("source_type") == "weakness_review"
        and task.get("status") == "pending"
        and isinstance(task.get("scheduled_date"), str)
        and task["scheduled_date"] >= today
    ]

    if not upcoming_tasks:
        return []

    next_review_date = min(
        task["scheduled_date"]
        for task in upcoming_tasks
    )

    return [
        task
        for task in upcoming_tasks
        if task["scheduled_date"] == next_review_date
    ]


def _render_learning_diagnostics(
    supabase,
    user_id: str,
    selected_plan: dict,
    plan_tasks: list[dict],
    today: str,
) -> None:
    """선택한 계획의 취약 개념과 다음 자동 복습을 간결하게 표시합니다."""

    st.markdown("### 학습 진단")

    try:
        course_key = normalize_course_key(
            selected_plan["course_name"]
        )
        concept_masteries = get_course_concept_masteries(
            supabase=supabase,
            user_id=user_id,
            course_key=course_key,
        )
    except Exception as error:
        st.warning(
            "개념 숙련도를 불러오지 못했습니다: "
            f"{error}"
        )
        concept_masteries = None

    weak_masteries = _get_priority_weak_masteries(
        concept_masteries or [],
    )
    next_review_tasks = _get_next_auto_review_tasks(
        plan_tasks=plan_tasks,
        today=today,
    )
    next_review_date = (
        next_review_tasks[0]["scheduled_date"]
        if next_review_tasks
        else None
    )
    next_review_minutes = sum(
        task["estimated_minutes"]
        for task in next_review_tasks
    )

    with st.container(border=True):
        if concept_masteries is None:
            st.caption("숙련도 정보를 확인하지 못했습니다.")
        elif not concept_masteries:
            st.caption(
                "아직 평가된 개념이 없습니다. 퀴즈를 응시하면 표시됩니다."
            )
        elif not weak_masteries:
            st.success("현재 취약 기준에 해당하는 개념이 없습니다.")
        else:
            st.caption(
                f"평가 {len(concept_masteries)}개 중 "
                f"취약 개념 {len(weak_masteries)}개"
            )
            for mastery in weak_masteries[:3]:
                mastery_score = mastery["mastery_score"]
                st.markdown(f"**{mastery['concept_name']}**")
                st.progress(
                    mastery_score,
                    text=f"숙련도 {mastery_score}/100",
                )
            if len(weak_masteries) > 3:
                st.caption(
                    f"그 외 취약 개념 {len(weak_masteries) - 3}개는 "
                    "과목별 숙련도 화면에서 확인할 수 있습니다."
                )

        st.markdown("**다음 자동 복습**")
        if not next_review_tasks:
            st.caption("현재 예정된 자동 복습 과제가 없습니다.")
        else:
            review_date_label = (
                "오늘"
                if next_review_date == today
                else next_review_date
            )
            st.caption(
                f"{review_date_label} · {len(next_review_tasks)}개 · "
                f"예상 {next_review_minutes}분"
            )
            for task in next_review_tasks[:2]:
                review_label = get_spaced_review_label(task)
                st.markdown(f"- {task['title']}")
                if review_label:
                    st.caption(review_label)


def _get_priority_weak_masteries(
    concept_masteries: list[dict],
) -> list[dict]:
    """취약 개념을 낮은 숙련도와 연속 오답 순으로 정렬합니다."""

    weak_masteries = [
        mastery
        for mastery in concept_masteries
        if mastery.get("is_weak") is True
    ]
    return sorted(
        weak_masteries,
        key=lambda mastery: (
            mastery.get("mastery_score", 100),
            -mastery.get("consecutive_incorrect_count", 0),
            mastery.get("concept_name", ""),
        ),
    )


def _build_today_tasks(
    plan_tasks: list[dict],
    selected_plan: dict,
    today: str,
) -> list[dict]:
    """오늘 과제에 화면에서 필요한 계획 문맥만 결합합니다."""

    today_tasks = []
    for task in plan_tasks:
        if task["scheduled_date"] != today:
            continue

        task_with_plan = dict(task)
        task_with_plan.update(
            {
                "plan_title": selected_plan["title"],
                "course_name": selected_plan["course_name"],
                "plan_id": selected_plan["id"],
                "goal": selected_plan["goal"],
                "current_level": selected_plan["current_level"],
            }
        )
        today_tasks.append(task_with_plan)

    return today_tasks


def _render_today_task_cards(
    supabase,
    user,
    today_tasks: list[dict],
) -> None:
    """오늘 과제를 카드로 표시하고 기존 완료 흐름을 유지합니다."""

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
                f"{task['course_name']} · {task['plan_title']} · "
                f"예상 {task['estimated_minutes']}분"
            )
            st.markdown(f"### {task_type} · {task['title']}")
            st.write(task["description"])

            review_label = get_spaced_review_label(task)
            if review_label:
                st.caption(review_label)

            if task["task_type"] in {"learn", "review"}:
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
                    "현재 퀴즈의 모든 문항을 맞히면 완료할 수 있습니다."
                    if quiz_completion_locked
                    else None
                ),
            ):
                try:
                    with st.spinner("과제 완료를 기록하고 있습니다..."):
                        result = complete_study_task(
                            supabase=supabase,
                            task_id=task["id"],
                        )

                    queue_gamification_notifications(
                        st.session_state,
                        result.get("gamification"),
                    )

                    if result["already_completed"]:
                        message = "이미 완료된 과제입니다."
                    else:
                        message = f"과제 완료! +{result['task_exp']} EXP"
                        if result["daily_bonus_exp"] > 0:
                            message += (
                                " · 오늘의 계획 완료 보너스 "
                                f"+{result['daily_bonus_exp']} EXP"
                            )
                        message += f" · 총 EXP {result['total_exp']}"

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
                        "과제 완료 처리에 실패했습니다: "
                        f"{error}"
                    )


def render_dashboard(supabase, user):
    st.header("오늘 학습")
    st.caption(
        "오늘 할 일과 학습 상태를 한 화면에서 확인하세요."
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

    today_tasks = _build_today_tasks(
        plan_tasks=plan_tasks,
        selected_plan=selected_plan,
        today=today,
    )

    if not today_tasks:
        task_column, insight_column = st.columns(
            [2, 1],
            gap="large",
            vertical_alignment="top",
        )

        with task_column:
            st.subheader("오늘 할 일")
            st.info(
                "선택한 계획에는 오늘 예정된 과제가 없습니다. "
                "다른 계획을 선택하거나 저장된 계획을 확인해보세요."
            )

        with insight_column:
            _render_learning_diagnostics(
                supabase=supabase,
                user_id=user.id,
                selected_plan=selected_plan,
                plan_tasks=plan_tasks,
                today=today,
            )
            render_gamification_dashboard_summary(
                supabase=supabase,
                user_id=str(user.id),
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
        st.columns(3, gap="medium")
    )

    metric_column1.metric(
        "이 계획의 오늘 과제",
        f"{total_count}개",
        border=True,
    )
    metric_column2.metric(
        "남은 과제",
        f"{remaining_count}개",
        border=True,
    )
    metric_column3.metric(
        "예상 학습시간",
        f"{total_minutes}분",
        border=True,
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

    task_list_column, task_detail_column, insight_column = st.columns(
        [1.05, 2.15, 1.15],
        gap="large",
        vertical_alignment="top",
    )

    task_by_id = {
        task["id"]: task
        for task in today_tasks
    }
    task_ids = list(task_by_id)
    if st.session_state.get(DASHBOARD_TASK_SELECT_KEY) not in task_by_id:
        first_pending_task = next(
            (
                task
                for task in today_tasks
                if task["status"] != "completed"
            ),
            today_tasks[0],
        )
        st.session_state[DASHBOARD_TASK_SELECT_KEY] = first_pending_task["id"]

    with task_list_column:
        st.subheader("오늘 할 일")
        selected_task_id = st.radio(
            "상세 내용을 확인할 과제",
            options=task_ids,
            key=DASHBOARD_TASK_SELECT_KEY,
            format_func=lambda task_id: get_dashboard_task_label(
                task_by_id[task_id]
            ),
            label_visibility="collapsed",
            persist_state="session",
        )
        st.caption(
            "과제를 선택하면 가운데 영역에 상세 내용이 표시됩니다."
        )

    with task_detail_column:
        st.subheader("선택한 과제")
        _render_today_task_cards(
            supabase=supabase,
            user=user,
            today_tasks=[task_by_id[selected_task_id]],
        )

    with insight_column:
        _render_learning_diagnostics(
            supabase=supabase,
            user_id=user.id,
            selected_plan=selected_plan,
            plan_tasks=plan_tasks,
            today=today,
        )
        render_gamification_dashboard_summary(
            supabase=supabase,
            user_id=str(user.id),
        )
