from datetime import date, timedelta

from supabase import Client

from models.study_plan import WeeklyStudyPlan


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

    plan_id = None

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

    plan_data = {
        "user_id": user_id,
        "title": plan.title[:100],
        "course_name": course_name.strip()[:100],
        "goal": goal.strip()[:1000],
        "current_level": current_level,
        "start_date": start_date.isoformat(),
        "target_date": (
            start_date + timedelta(days=6)
        ).isoformat(),
        "available_schedule": available_schedule,
        "weekly_overview": weekly_overview,
        "status": "active",
    }

    try:
        plan_response = (
            supabase.table("study_plans")
            .insert(plan_data)
            .execute()
        )

        if not plan_response.data:
            raise RuntimeError("학습계획 저장 결과가 비어 있습니다.")

        saved_plan = plan_response.data[0]
        plan_id = saved_plan["id"]

        task_data = []

        for day in plan.days:
            scheduled_date = (
                start_date + timedelta(days=day.day_offset)
            )

            for task in day.tasks:
                task_data.append(
                    {
                        "user_id": user_id,
                        "plan_id": plan_id,
                        "scheduled_date": scheduled_date.isoformat(),
                        "title": task.title[:200],
                        "description": task.description,
                        "task_type": task.task_type,
                        "estimated_minutes": task.estimated_minutes,
                        "status": "pending",
                    }
                )

        if task_data:
            (
                supabase.table("study_tasks")
                .insert(task_data)
                .execute()
            )

        return saved_plan

    except Exception:
        if plan_id is not None:
            try:
                (
                    supabase.table("study_plans")
                    .delete()
                    .eq("id", plan_id)
                    .eq("user_id", user_id)
                    .execute()
                )
            except Exception:
                pass

        raise

def get_user_study_plans(
    supabase: Client,
    user_id: str,
) -> list[dict]:
    """사용자의 학습계획을 최신순으로 불러옵니다."""

    response = (
        supabase.table("study_plans")
        .select(
            "id, title, course_name, goal, current_level, "
            "start_date, target_date, status, created_at"
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
        .select(
            "id, scheduled_date, title, description, "
            "task_type, estimated_minutes, status, "
            "source_type, concept_id, review_stage, "
            "review_interval_days"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .order("scheduled_date")
        .order("created_at")
        .execute()
    )

    return response.data or []

def complete_study_task(
    supabase: Client,
    task_id: str,
) -> dict:
    """과제를 완료하고 EXP와 연속 학습 정보를 갱신합니다."""

    response = (
        supabase.rpc(
            "complete_study_task",
            {
                "p_task_id": task_id,
            },
        )
        .execute()
    )

    if response.data is None:
        raise RuntimeError("과제 완료 처리 결과가 비어 있습니다.")

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
