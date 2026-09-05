from uuid import UUID

from supabase import Client

from services.learning_objective_repository import (
    get_learning_objectives_by_plan_ids,
)


def _normalize_uuid(value: str, field_name: str) -> str:
    """조회 경계에서 UUID 형식을 검증합니다."""

    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} 형식이 올바르지 않습니다.") from None


def _validate_owned_rows(
    rows: list[dict],
    *,
    user_id: str,
    record_name: str,
) -> list[dict]:
    """조회 결과가 요청 사용자에게만 속하는지 다시 확인합니다."""

    if any(str(row.get("user_id")) != user_id for row in rows):
        raise RuntimeError(
            f"{record_name} 조회 결과의 사용자 소유권이 올바르지 않습니다."
        )
    return rows


def get_learning_performance_data(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> dict:
    """본인 계획의 성과 계산에 필요한 최소 기록을 일괄 조회합니다."""

    normalized_user_id = _normalize_uuid(user_id, "사용자 ID")
    normalized_plan_id = _normalize_uuid(plan_id, "학습계획 ID")

    plan_response = (
        supabase.table("study_plans")
        .select(
            "id, user_id, title, course_name, goal, current_level, "
            "start_date, target_date, status"
        )
        .eq("id", normalized_plan_id)
        .eq("user_id", normalized_user_id)
        .limit(1)
        .execute()
    )
    if not plan_response.data:
        raise RuntimeError("학습 성과를 확인할 본인 계획을 찾을 수 없습니다.")
    plan = plan_response.data[0]
    if str(plan.get("user_id")) != normalized_user_id:
        raise RuntimeError("학습계획 조회 결과의 사용자 소유권이 올바르지 않습니다.")

    tasks_response = (
        supabase.table("study_tasks")
        .select(
            "id, user_id, plan_id, learning_objective_id, scheduled_date, "
            "title, task_type, estimated_minutes, status, completed_at"
        )
        .eq("user_id", normalized_user_id)
        .eq("plan_id", normalized_plan_id)
        .order("scheduled_date")
        .order("created_at")
        .execute()
    )
    tasks = _validate_owned_rows(
        tasks_response.data or [],
        user_id=normalized_user_id,
        record_name="학습과제",
    )
    if any(str(task.get("plan_id")) != normalized_plan_id for task in tasks):
        raise RuntimeError("학습과제 조회 결과의 계획 연결이 올바르지 않습니다.")

    quizzes_response = (
        supabase.table("quizzes")
        .select(
            "id, user_id, plan_id, task_id, title, learning_objective_id, "
            "created_at"
        )
        .eq("user_id", normalized_user_id)
        .eq("plan_id", normalized_plan_id)
        .order("created_at")
        .execute()
    )
    quizzes = _validate_owned_rows(
        quizzes_response.data or [],
        user_id=normalized_user_id,
        record_name="퀴즈",
    )
    if any(str(quiz.get("plan_id")) != normalized_plan_id for quiz in quizzes):
        raise RuntimeError("퀴즈 조회 결과의 계획 연결이 올바르지 않습니다.")

    quiz_ids = [str(quiz["id"]) for quiz in quizzes]
    attempts: list[dict] = []
    if quiz_ids:
        attempts_response = (
            supabase.table("quiz_attempts")
            .select(
                "id, user_id, quiz_id, attempt_number, correct_count, "
                "total_questions, score, submitted_at"
            )
            .eq("user_id", normalized_user_id)
            .in_("quiz_id", quiz_ids)
            .order("submitted_at")
            .execute()
        )
        attempts = _validate_owned_rows(
            attempts_response.data or [],
            user_id=normalized_user_id,
            record_name="퀴즈 응시",
        )
        if any(str(attempt.get("quiz_id")) not in quiz_ids for attempt in attempts):
            raise RuntimeError("퀴즈 응시 조회 결과의 퀴즈 연결이 올바르지 않습니다.")

    attempt_ids = [str(attempt["id"]) for attempt in attempts]
    mastery_events: list[dict] = []
    if attempt_ids:
        events_response = (
            supabase.table("concept_mastery_events")
            .select(
                "id, user_id, concept_id, quiz_id, quiz_attempt_id, "
                "question_index, is_correct, score_before, score_delta, "
                "score_after, created_at"
            )
            .eq("user_id", normalized_user_id)
            .in_("quiz_attempt_id", attempt_ids)
            .order("created_at")
            .order("question_index")
            .execute()
        )
        mastery_events = _validate_owned_rows(
            events_response.data or [],
            user_id=normalized_user_id,
            record_name="숙련도 변화",
        )
        if any(
            str(event.get("quiz_attempt_id")) not in attempt_ids
            for event in mastery_events
        ):
            raise RuntimeError("숙련도 변화의 응시 연결이 올바르지 않습니다.")

    concept_ids = list(
        dict.fromkeys(
            str(event["concept_id"])
            for event in mastery_events
            if event.get("concept_id") is not None
        )
    )
    concepts: list[dict] = []
    current_masteries: list[dict] = []
    if concept_ids:
        concepts_response = (
            supabase.table("learning_concepts")
            .select("id, user_id, canonical_name")
            .eq("user_id", normalized_user_id)
            .in_("id", concept_ids)
            .execute()
        )
        concepts = _validate_owned_rows(
            concepts_response.data or [],
            user_id=normalized_user_id,
            record_name="학습 개념",
        )

        mastery_response = (
            supabase.table("concept_mastery")
            .select(
                "user_id, concept_id, mastery_score, "
                "consecutive_incorrect_count, last_assessed_at"
            )
            .eq("user_id", normalized_user_id)
            .in_("concept_id", concept_ids)
            .execute()
        )
        current_masteries = _validate_owned_rows(
            mastery_response.data or [],
            user_id=normalized_user_id,
            record_name="현재 숙련도",
        )

    objectives = get_learning_objectives_by_plan_ids(
        supabase=supabase,
        user_id=normalized_user_id,
        plan_ids=[normalized_plan_id],
    )[normalized_plan_id]

    return {
        "plan": plan,
        "tasks": tasks,
        "objectives": objectives,
        "quizzes": quizzes,
        "attempts": attempts,
        "mastery_events": mastery_events,
        "concepts": concepts,
        "current_masteries": current_masteries,
    }
