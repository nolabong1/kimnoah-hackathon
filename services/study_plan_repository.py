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