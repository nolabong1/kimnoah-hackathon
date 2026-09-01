from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.concept_service import normalize_course_key
from services.dashboard_repository import get_dashboard_snapshot
from services.study_plan_repository import (
    complete_study_task,
    get_user_study_plans,
)
from views.completion_feedback import render_completion_feedback
from views.error_feedback import render_unexpected_error
from views.focus_sprint_component import (
    apply_focus_completion_request,
    render_focus_sprint,
)
from views.gamification_state import queue_gamification_notifications
from views.gamification_view import (
    render_gamification_dashboard_summary_from_data,
)
from views.interaction_state import queue_task_completion_interactions
from views.learning_flow_state import (
    DASHBOARD_PENDING_TASK_KEY,
    TASK_FLOW_STAGES,
    TASK_STAGE_COMPLETE,
    TASK_STAGE_CONTENT,
    TASK_STAGE_OVERVIEW,
    get_default_task_stage,
    get_next_pending_task_id,
    get_task_stage_key,
    get_task_stage_label,
)
from views.learning_context_state import request_tutor_learning_context
from views.learning_momentum_component import (
    build_learning_momentum,
    render_learning_momentum,
)
from views.learning_quest_map_component import (
    apply_quest_map_selection,
    build_learning_quest_nodes,
    render_learning_quest_map,
)
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


DASHBOARD_PLAN_SELECT_KEY = "dashboard_selected_plan_id"
DASHBOARD_TASK_SELECT_KEY = "dashboard_selected_task_id"
DASHBOARD_QUEST_MAP_KEY_PREFIX = "dashboard_learning_quest_map"


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
    concept_masteries: list[dict],
    plan_tasks: list[dict],
    today: str,
) -> None:
    """선택한 계획의 취약 개념과 다음 자동 복습을 간결하게 표시합니다."""

    st.subheader("학습 진단")

    weak_masteries = _get_priority_weak_masteries(
        concept_masteries,
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
        if not concept_masteries:
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


def _render_today_task_card(
    supabase,
    user,
    task: dict,
    today_tasks: list[dict],
) -> None:
    """선택한 오늘 과제를 안내·콘텐츠·완료 단계로 표시합니다."""

    task_type_names = {
        "learn": ":material/menu_book: 학습",
        "review": ":material/replay: 복습",
        "quiz": ":material/quiz: 퀴즈",
    }

    task_type = task_type_names.get(
        task["task_type"],
        ":material/assignment: 과제",
    )
    stage_key = get_task_stage_key("dashboard", str(task["id"]))
    if st.session_state.get(stage_key) not in TASK_FLOW_STAGES:
        st.session_state[stage_key] = get_default_task_stage(task)

    with st.container(border=True):
        st.caption(
            f"{task['course_name']} · {task['plan_title']} · "
            f"예상 {task['estimated_minutes']}분"
        )
        st.markdown(f"### {task_type} · {task['title']}")
        if st.button(
            "이 과제로 AI 튜터에게 질문하기",
            key=f"dashboard_open_tutor_{task['id']}",
            icon=":material/psychology:",
            width="stretch",
            help="선택한 계획과 과제를 유지한 채 단계별 힌트 튜터로 이동합니다.",
        ):
            request_tutor_learning_context(
                st.session_state,
                plan_id=str(task["plan_id"]),
                task_id=str(task["id"]),
                source="today",
            )
            st.rerun()

        selected_stage = st.segmented_control(
            "학습 단계",
            options=TASK_FLOW_STAGES,
            format_func=lambda stage: get_task_stage_label(
                stage,
                task["task_type"],
            ),
            key=stage_key,
            required=True,
            width="stretch",
            persist_state="session",
        )

        if selected_stage == TASK_STAGE_OVERVIEW:
            st.write(task["description"])
            review_label = get_spaced_review_label(task)
            if review_label:
                st.caption(review_label)
            if task["status"] == "completed":
                st.success(
                    "이미 완료한 과제입니다. 학습자료를 다시 확인할 수 있습니다.",
                    icon=":material/check_circle:",
                )
            else:
                st.info(
                    "과제 내용을 확인했다면 다음 단계에서 학습을 시작하세요.",
                    icon=":material/arrow_forward:",
                )
            return

        if selected_stage == TASK_STAGE_CONTENT:
            focus_sprint_key = f"dashboard_focus_sprint_{task['id']}"
            render_focus_sprint(
                task,
                key=focus_sprint_key,
                on_ready_to_complete_task_id_change=lambda: (
                    apply_focus_completion_request(
                        st.session_state,
                        component_key=focus_sprint_key,
                        stage_key=stage_key,
                        expected_task_id=str(task["id"]),
                    )
                ),
            )
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
                    display_mode="open",
                )
            elif task["task_type"] == "quiz":
                render_quiz_section(
                    supabase=supabase,
                    user_id=user.id,
                    plan_id=task["plan_id"],
                    course_name=task["course_name"],
                    goal=task["goal"],
                    current_level=task["current_level"],
                    task=task,
                    widget_scope="dashboard",
                    display_mode="open",
                )
            return

        if selected_stage != TASK_STAGE_COMPLETE:
            return

        quiz_completion_unlocked = True
        if task["task_type"] == "quiz":
            quiz_completion_unlocked = render_quiz_section(
                supabase=supabase,
                user_id=user.id,
                plan_id=task["plan_id"],
                course_name=task["course_name"],
                goal=task["goal"],
                current_level=task["current_level"],
                task=task,
                widget_scope="dashboard",
                display_mode="status_only",
            )

        if task["status"] == "completed":
            st.success(
                "완료된 과제입니다.",
                icon=":material/check_circle:",
            )
            return

        quiz_completion_locked = (
            task["task_type"] == "quiz"
            and not quiz_completion_unlocked
        )
        if not quiz_completion_locked:
            st.caption(
                "학습을 마쳤다면 완료를 기록하고 EXP를 받아보세요."
            )

        if not st.button(
            "과제 완료하기",
            key=f"dashboard_complete_{task['id']}",
            type="primary",
            icon=":material/task_alt:",
            width="stretch",
            disabled=quiz_completion_locked,
            help=(
                "현재 퀴즈의 모든 문항을 맞히면 완료할 수 있습니다."
                if quiz_completion_locked
                else None
            ),
        ):
            return

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
            queue_task_completion_interactions(
                st.session_state,
                task_id=task["id"],
                result=result,
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

            next_task_id = get_next_pending_task_id(
                today_tasks,
                str(task["id"]),
            )
            next_task = next(
                (
                    candidate
                    for candidate in today_tasks
                    if candidate.get("id") == next_task_id
                ),
                None,
            )
            if next_task_id is not None:
                st.session_state[DASHBOARD_PENDING_TASK_KEY] = next_task_id
                next_stage_key = get_task_stage_key(
                    "dashboard",
                    next_task_id,
                )
                st.session_state[next_stage_key] = TASK_STAGE_OVERVIEW

            st.session_state.task_completion_feedback = {
                "message": message,
                "daily_bonus_exp": result.get(
                    "daily_bonus_exp",
                    0,
                ),
                "guided_flow": True,
                "next_task_title": (
                    next_task.get("title")
                    if isinstance(next_task, dict)
                    else None
                ),
            }
            st.rerun()
        except Exception as error:
            render_unexpected_error(
                error,
                operation="dashboard.complete_task",
                user_message=(
                    "과제 완료 처리에 실패했습니다. 잠시 후 다시 "
                    "시도해주세요."
                ),
            )


def render_dashboard(supabase, user, profile: dict | None = None):
    render_page_header(
        "오늘 학습",
        "오늘 할 일과 학습 상태를 한 화면에서 확인하세요.",
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
        render_unexpected_error(
            error,
            operation="dashboard.load_plans",
            user_message=(
                "학습계획을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not saved_plans:
        render_empty_state(
            "저장된 학습계획이 없습니다",
            "먼저 새로운 계획을 만들어 저장해보세요.",
            icon=":material/event_note:",
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
        dashboard_snapshot = get_dashboard_snapshot(
            supabase=supabase,
            user_id=user.id,
            plan_id=selected_plan_id,
            course_key=normalize_course_key(
                selected_plan["course_name"]
            ),
        )

    except Exception as error:
        if _is_missing_dashboard_snapshot_rpc(error):
            user_message = (
                "오늘 학습 통합 조회 설정이 아직 적용되지 않았습니다. "
                "Supabase SQL Editor에서 "
                "supabase_dashboard_snapshot.sql을 실행해주세요."
            )
        else:
            user_message = (
                "오늘 학습 요약을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            )
        render_unexpected_error(
            error,
            operation="dashboard.load_snapshot",
            user_message=user_message,
        )
        return

    plan_tasks = dashboard_snapshot["plan_tasks"]
    concept_masteries = dashboard_snapshot["concept_masteries"]

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
            render_empty_state(
                "오늘 예정된 과제가 없습니다",
                "다른 계획을 선택하거나 저장된 계획을 확인해보세요.",
                icon=":material/event_available:",
            )

        with insight_column:
            _render_learning_diagnostics(
                concept_masteries=concept_masteries,
                plan_tasks=plan_tasks,
                today=today,
            )
            render_gamification_dashboard_summary_from_data(
                achievements=dashboard_snapshot["achievements"],
                challenges=dashboard_snapshot["challenges"],
                showcase=dashboard_snapshot["badge_showcase"],
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

    render_metric_row(
        [
            MetricItem(
                "이 계획의 오늘 과제",
                f"{total_count}개",
                icon=":material/checklist:",
            ),
            MetricItem(
                "남은 과제",
                f"{remaining_count}개",
                icon=":material/pending_actions:",
            ),
            MetricItem(
                "예상 학습시간",
                f"{total_minutes}분",
                icon=":material/schedule:",
            ),
        ]
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
            "선택한 계획의 오늘 학습을 모두 완료했습니다!",
            icon=":material/celebration:",
        )
    else:
        st.write(
            f"오늘 완료까지 **{remaining_count}개** 남았습니다."
        )

    if profile is not None:
        momentum = build_learning_momentum(
            profile,
            completed_tasks=completed_count,
            total_tasks=total_count,
        )
        render_learning_momentum(
            momentum,
            key=f"dashboard_learning_momentum_{user.id}",
        )

    task_by_id = {
        task["id"]: task
        for task in today_tasks
    }
    task_ids = list(task_by_id)
    pending_task_id = st.session_state.pop(
        DASHBOARD_PENDING_TASK_KEY,
        None,
    )
    if (
        pending_task_id in task_by_id
        and task_by_id[pending_task_id]["status"] != "completed"
    ):
        st.session_state[DASHBOARD_TASK_SELECT_KEY] = pending_task_id
    elif st.session_state.get(DASHBOARD_TASK_SELECT_KEY) not in task_by_id:
        first_pending_task = next(
            (
                task
                for task in today_tasks
                if task["status"] != "completed"
            ),
            today_tasks[0],
        )
        st.session_state[DASHBOARD_TASK_SELECT_KEY] = first_pending_task["id"]

    selected_task_id = st.session_state[DASHBOARD_TASK_SELECT_KEY]
    quest_map_key = (
        f"{DASHBOARD_QUEST_MAP_KEY_PREFIX}_{selected_plan_id}_{today}"
    )
    quest_nodes = build_learning_quest_nodes(
        today_tasks,
        selected_task_id,
    )
    render_learning_quest_map(
        quest_nodes,
        key=quest_map_key,
        on_selected_task_id_change=lambda: apply_quest_map_selection(
            st.session_state,
            component_key=quest_map_key,
            selection_key=DASHBOARD_TASK_SELECT_KEY,
            allowed_task_ids=task_ids,
        ),
    )
    st.caption(
        "퀘스트 노드를 누르면 아래의 선택 과제와 상세 내용이 함께 바뀝니다."
    )

    task_list_column, task_detail_column, insight_column = st.columns(
        [1.05, 2.15, 1.15],
        gap="large",
        vertical_alignment="top",
    )

    with task_list_column:
        with st.container(border=True):
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
        _render_today_task_card(
            supabase=supabase,
            user=user,
            task=task_by_id[selected_task_id],
            today_tasks=today_tasks,
        )

    with insight_column:
        _render_learning_diagnostics(
            concept_masteries=concept_masteries,
            plan_tasks=plan_tasks,
            today=today,
        )
        render_gamification_dashboard_summary_from_data(
            achievements=dashboard_snapshot["achievements"],
            challenges=dashboard_snapshot["challenges"],
            showcase=dashboard_snapshot["badge_showcase"],
        )


def _is_missing_dashboard_snapshot_rpc(error: Exception) -> bool:
    """통합 조회 마이그레이션 누락 오류인지 판별합니다."""

    message = str(error)
    return "get_dashboard_snapshot" in message and any(
        marker in message
        for marker in ("PGRST202", "schema cache", "Could not find")
    )
