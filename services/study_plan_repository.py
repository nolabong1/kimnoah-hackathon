from datetime import date

from supabase import Client

from models.study_plan import WeeklyStudyPlan
from services.gamification_repository import (
    validate_gamification_sync_result,
)


STUDY_TASK_SELECT_FIELDS = (
    "id, scheduled_date, title, description, "
    "task_type, estimated_minutes, status, "
    "source_type, concept_id, review_stage, "
    "review_interval_days"
)


def save_weekly_study_plan(
    supabase: Client,
    user_id: str,
    plan: WeeklyStudyPlan,
    course_name: str,
    goal: str,
    current_level: int,
    start_date: date,
    available_schedule: dict[str, int],
) -> dict:
    """학습계획과 상세 과제를 Supabase에 저장합니다."""

    weekly_overview = [
        {
            "day_offset": day.day_offset,
            "daily_focus": day.daily_focus,
            "total_minutes": sum(
                task.estimated_minutes for task in day.tasks
            ),
        }
        for day in plan.days
    ]

    tasks = [
        {
            "day_offset": day.day_offset,
            "title": task.title[:200],
            "description": task.description,
            "task_type": task.task_type,
            "estimated_minutes": task.estimated_minutes,
        }
        for day in plan.days
        for task in day.tasks
    ]

    response = (
        supabase.rpc(
            "save_weekly_study_plan_with_tasks",
            {
                "p_title": plan.title[:100],
                "p_course_name": course_name.strip()[:100],
                "p_goal": goal.strip()[:1000],
                "p_current_level": current_level,
                "p_start_date": start_date.isoformat(),
                "p_available_schedule": available_schedule,
                "p_weekly_overview": weekly_overview,
                "p_tasks": tasks,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError("학습계획 저장 결과가 비어 있습니다.")
    if response.data.get("user_id") != user_id:
        raise RuntimeError("저장된 학습계획의 사용자 정보가 올바르지 않습니다.")

    return response.data

def get_user_study_plans(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자의 학습계획을 최신순으로 불러옵니다."""

    response = (
        supabase.table("study_plans")
        .select(
            "id, title, course_name, goal, current_level, "
            "start_date, target_date, available_schedule, "
            "weekly_overview, status, created_at"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    return response.data or []


def delete_study_plan(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> dict:
    """사용자 본인의 학습계획과 연결된 데이터를 삭제합니다."""

    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("사용자 ID가 필요합니다.")

    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError("학습계획 ID가 필요합니다.")

    response = (
        supabase.table("study_plans")
        .delete()
        .eq("id", plan_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "삭제할 학습계획을 찾을 수 없습니다."
        )

    return response.data[0]


def get_study_plan_tasks(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> list[dict]:
    """선택한 학습계획의 상세 과제를 불러옵니다."""

    response = (
        supabase.table("study_tasks")
        .select(STUDY_TASK_SELECT_FIELDS)
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .order("scheduled_date")
        .order("created_at")
        .execute()
    )

    return response.data or []


def get_study_tasks_by_plan_ids(
    supabase: Client,
    user_id: str,
    plan_ids: list[str],
) -> dict[str, list[dict]]:
    """여러 학습계획의 과제를 한 번에 조회해 계획별로 묶습니다."""

    normalized_plan_ids = list(
        dict.fromkeys(
            plan_id.strip()
            for plan_id in plan_ids
            if isinstance(plan_id, str) and plan_id.strip()
        )
    )
    tasks_by_plan = {
        plan_id: [] for plan_id in normalized_plan_ids
    }
    if not normalized_plan_ids:
        return tasks_by_plan

    response = (
        supabase.table("study_tasks")
        .select(f"plan_id, {STUDY_TASK_SELECT_FIELDS}")
        .eq("user_id", user_id)
        .in_("plan_id", normalized_plan_ids)
        .order("scheduled_date")
        .order("created_at")
        .execute()
    )

    for task in response.data or []:
        plan_id = task.get("plan_id")
        if plan_id in tasks_by_plan:
            tasks_by_plan[plan_id].append(task)

    return tasks_by_plan


def complete_study_task(
    supabase: Client,
    task_id: str,
) -> dict:
    """과제를 완료하고 EXP와 연속 학습 정보를 갱신합니다."""

    response = (
        supabase.rpc(
            "complete_study_task_with_gamification",
            {
                "p_task_id": task_id,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError("과제 완료 처리 결과가 비어 있습니다.")

    normalized_result = dict(response.data)
    normalized_result["gamification"] = (
        validate_gamification_sync_result(
            response.data.get("gamification")
        )
    )
    return normalized_result


def complete_study_plan_for_weekly_review_test(
    supabase: Client,
    plan_id: str,
) -> dict:
    """본인 계획의 미완료 과제와 기존 보상을 테스트용으로 일괄 처리합니다."""

    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError("테스트 완료할 학습계획 ID가 필요합니다.")

    response = (
        supabase.rpc(
            "complete_study_plan_for_weekly_review_test",
            {
                "p_plan_id": plan_id,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError("학습계획 테스트 완료 결과가 비어 있습니다.")

    required_fields = {
        "plan_id",
        "completed_task_count",
        "task_exp",
        "daily_bonus_exp",
        "total_exp",
        "level",
        "current_streak",
        "already_completed",
    }
    if not required_fields.issubset(response.data):
        raise RuntimeError("학습계획 테스트 완료 응답 형식이 올바르지 않습니다.")

    if str(response.data["plan_id"]) != plan_id:
        raise RuntimeError("학습계획 테스트 완료 응답의 계획 ID가 다릅니다.")

    numeric_fields = {
        "completed_task_count",
        "task_exp",
        "daily_bonus_exp",
        "total_exp",
        "level",
        "current_streak",
    }
    if any(
        not isinstance(response.data[field], int)
        or isinstance(response.data[field], bool)
        or response.data[field] < 0
        for field in numeric_fields
    ) or not isinstance(response.data["already_completed"], bool):
        raise RuntimeError("학습계획 테스트 완료 응답 값이 올바르지 않습니다.")

    return response.data

def reset_today_test_progress(
    supabase: Client,
) -> dict:
    """오늘의 과제·보상·퀴즈·숙련도 테스트 기록을 초기화합니다."""

    response = (
        supabase.rpc(
            "reset_today_test_progress",
            {},
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError(
            "테스트 초기화 결과가 비어 있습니다."
        )

    return response.data
