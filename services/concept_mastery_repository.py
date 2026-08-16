from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.concept_mastery import (
    AdaptiveQuizAnalysis,
    ConceptMasterySummary,
)


def _normalize_uuid(value: str, field_name: str) -> str:
    """외부 조회 식별자를 UUID 문자열로 검증하고 정규화합니다."""

    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            f"{field_name} 형식이 올바르지 않습니다."
        ) from None


def get_current_weak_concepts(
    supabase: Client,
) -> list[dict]:
    """로그인 사용자의 현재 취약 개념을 서버 판정 결과로 조회합니다."""

    response = (
        supabase.rpc("get_current_weak_concepts")
        .execute()
    )

    if not isinstance(response.data, list):
        raise RuntimeError(
            "취약 개념 조회 결과 형식이 올바르지 않습니다."
        )

    try:
        weak_concepts = [
            ConceptMasterySummary.model_validate(concept)
            for concept in response.data
        ]
    except ValidationError as error:
        raise RuntimeError(
            "저장된 취약 개념 데이터 형식이 올바르지 않습니다."
        ) from error

    return [
        concept.model_dump(mode="json")
        for concept in weak_concepts
    ]


def get_course_concept_masteries(
    supabase: Client,
    user_id: str,
    course_key: str,
) -> list[dict]:
    """선택한 과목에서 평가된 개념별 현재 숙련도를 조회합니다."""

    normalized_user_id = _normalize_uuid(
        user_id,
        "사용자 ID",
    )

    if (
        not isinstance(course_key, str)
        or not 1 <= len(course_key.strip()) <= 120
    ):
        raise ValueError("과목 키 형식이 올바르지 않습니다.")

    normalized_course_key = course_key.strip()
    concepts_response = (
        supabase.table("learning_concepts")
        .select(
            "id, course_key, concept_key, canonical_name"
        )
        .eq("user_id", normalized_user_id)
        .eq("course_key", normalized_course_key)
        .execute()
    )
    concepts = concepts_response.data or []

    if not isinstance(concepts, list):
        raise RuntimeError(
            "과목 개념 조회 결과가 올바르지 않습니다."
        )

    concepts_by_id = {
        concept["id"]: concept
        for concept in concepts
        if isinstance(concept, dict)
        and isinstance(concept.get("id"), str)
    }

    if not concepts_by_id:
        return []

    mastery_response = (
        supabase.table("concept_mastery")
        .select(
            "concept_id, mastery_score, correct_count, "
            "incorrect_count, consecutive_incorrect_count, "
            "last_answer_correct, last_assessed_at"
        )
        .eq("user_id", normalized_user_id)
        .in_("concept_id", list(concepts_by_id))
        .execute()
    )
    masteries = mastery_response.data or []

    if not isinstance(masteries, list):
        raise RuntimeError(
            "과목 숙련도 조회 결과가 올바르지 않습니다."
        )

    if not masteries:
        return []

    weak_concept_ids = {
        concept["concept_id"]
        for concept in get_current_weak_concepts(
            supabase=supabase,
        )
        if concept.get("course_key")
        == normalized_course_key
    }
    dashboard_masteries = []

    try:
        for mastery in masteries:
            if not isinstance(mastery, dict):
                raise ValueError

            concept_id = mastery.get("concept_id")
            concept = concepts_by_id.get(concept_id)

            if concept is None:
                raise ValueError

            summary = ConceptMasterySummary.model_validate(
                {
                    "concept_id": concept_id,
                    "course_key": concept["course_key"],
                    "concept_key": concept["concept_key"],
                    "concept_name": concept[
                        "canonical_name"
                    ],
                    "mastery_score": mastery[
                        "mastery_score"
                    ],
                    "correct_count": mastery["correct_count"],
                    "incorrect_count": mastery[
                        "incorrect_count"
                    ],
                    "consecutive_incorrect_count": mastery[
                        "consecutive_incorrect_count"
                    ],
                    "last_answer_correct": mastery[
                        "last_answer_correct"
                    ],
                    "last_assessed_at": mastery[
                        "last_assessed_at"
                    ],
                }
            ).model_dump(mode="json")
            summary["is_weak"] = (
                concept_id in weak_concept_ids
            )
            dashboard_masteries.append(summary)

    except (KeyError, ValidationError, ValueError) as error:
        raise RuntimeError(
            "저장된 과목 숙련도 형식이 올바르지 않습니다."
        ) from error

    return sorted(
        dashboard_masteries,
        key=lambda mastery: (
            not mastery["is_weak"],
            mastery["mastery_score"],
            mastery["concept_name"],
        ),
    )


def get_quiz_attempt_analysis(
    supabase: Client,
    user_id: str,
    plan_id: str,
    quiz_attempt_id: str,
) -> dict:
    """저장된 응시의 숙련도 변화와 연결된 복습 일정을 조회합니다."""

    normalized_user_id = _normalize_uuid(
        user_id,
        "사용자 ID",
    )
    normalized_plan_id = _normalize_uuid(
        plan_id,
        "학습계획 ID",
    )
    normalized_attempt_id = _normalize_uuid(
        quiz_attempt_id,
        "퀴즈 응시 ID",
    )

    events_response = (
        supabase.table("concept_mastery_events")
        .select(
            "concept_id, question_index, is_correct, "
            "score_before, score_delta, score_after"
        )
        .eq("user_id", normalized_user_id)
        .eq("quiz_attempt_id", normalized_attempt_id)
        .order("question_index")
        .execute()
    )
    events = events_response.data or []

    if not isinstance(events, list):
        raise RuntimeError(
            "숙련도 변경 이력 조회 결과가 올바르지 않습니다."
        )

    concept_ids = list(
        dict.fromkeys(
            event.get("concept_id")
            for event in events
            if isinstance(event, dict)
            and isinstance(event.get("concept_id"), str)
        )
    )

    if not concept_ids:
        return AdaptiveQuizAnalysis(
            attempt_id=normalized_attempt_id,
        ).model_dump(mode="json")

    concepts_response = (
        supabase.table("learning_concepts")
        .select(
            "id, course_key, concept_key, canonical_name"
        )
        .eq("user_id", normalized_user_id)
        .in_("id", concept_ids)
        .execute()
    )
    mastery_response = (
        supabase.table("concept_mastery")
        .select(
            "concept_id, mastery_score, correct_count, "
            "incorrect_count, consecutive_incorrect_count, "
            "last_answer_correct, last_assessed_at"
        )
        .eq("user_id", normalized_user_id)
        .in_("concept_id", concept_ids)
        .execute()
    )

    concepts = concepts_response.data or []
    masteries = mastery_response.data or []

    if not isinstance(concepts, list) or not isinstance(
        masteries,
        list,
    ):
        raise RuntimeError(
            "개념 숙련도 조회 결과가 올바르지 않습니다."
        )

    concepts_by_id = {
        concept["id"]: concept
        for concept in concepts
        if isinstance(concept, dict)
        and isinstance(concept.get("id"), str)
    }
    masteries_by_id = {
        mastery["concept_id"]: mastery
        for mastery in masteries
        if isinstance(mastery, dict)
        and isinstance(mastery.get("concept_id"), str)
    }

    if any(
        concept_id not in concepts_by_id
        or concept_id not in masteries_by_id
        for concept_id in concept_ids
    ):
        raise RuntimeError(
            "응시 문항에 연결된 개념 숙련도를 찾을 수 없습니다."
        )

    current_weak_concepts = get_current_weak_concepts(
        supabase=supabase,
    )
    weak_concepts = [
        concept
        for concept in current_weak_concepts
        if concept.get("concept_id") in concept_ids
    ]
    weak_concept_ids = {
        concept["concept_id"]
        for concept in weak_concepts
    }

    concept_masteries = []

    for concept_id in concept_ids:
        concept = concepts_by_id[concept_id]
        mastery = masteries_by_id[concept_id]
        concept_masteries.append(
            {
                "concept_id": concept_id,
                "course_key": concept["course_key"],
                "concept_key": concept["concept_key"],
                "concept_name": concept["canonical_name"],
                "mastery_score": mastery["mastery_score"],
                "correct_count": mastery["correct_count"],
                "incorrect_count": mastery["incorrect_count"],
                "consecutive_incorrect_count": mastery[
                    "consecutive_incorrect_count"
                ],
                "last_answer_correct": mastery[
                    "last_answer_correct"
                ],
                "last_assessed_at": mastery[
                    "last_assessed_at"
                ],
            }
        )

    mastery_changes = []

    for event in events:
        if not isinstance(event, dict):
            raise RuntimeError(
                "숙련도 변경 이력 형식이 올바르지 않습니다."
            )

        concept_id = event.get("concept_id")
        concept = concepts_by_id.get(concept_id)

        if concept is None:
            raise RuntimeError(
                "숙련도 변경 이력의 개념을 찾을 수 없습니다."
            )

        mastery_changes.append(
            {
                **event,
                "concept_key": concept["concept_key"],
                "concept_name": concept["canonical_name"],
                "is_weak": concept_id in weak_concept_ids,
            }
        )

    eligible_review_concept_ids = [
        concept["concept_id"]
        for concept in weak_concepts
        if concept["incorrect_count"] >= 2
        and any(
            event.get("concept_id") == concept["concept_id"]
            and event.get("is_correct") is False
            for event in events
            if isinstance(event, dict)
        )
    ]
    review_tasks = []

    if eligible_review_concept_ids:
        tasks_response = (
            supabase.table("study_tasks")
            .select(
                "id, plan_id, concept_id, title, "
                "scheduled_date, estimated_minutes, status, "
                "source_quiz_attempt_id, review_stage, "
                "review_interval_days"
            )
            .eq("user_id", normalized_user_id)
            .eq("plan_id", normalized_plan_id)
            .eq("source_type", "weakness_review")
            .in_("concept_id", eligible_review_concept_ids)
            .order("scheduled_date")
            .order("created_at")
            .execute()
        )
        tasks = tasks_response.data or []

        if not isinstance(tasks, list):
            raise RuntimeError(
                "자동 복습 과제 조회 결과가 올바르지 않습니다."
            )

        for task in tasks:
            if not isinstance(task, dict):
                raise RuntimeError(
                    "자동 복습 과제 형식이 올바르지 않습니다."
                )

            if (
                task.get("source_quiz_attempt_id")
                != normalized_attempt_id
                and task.get("status") != "pending"
            ):
                continue

            concept = concepts_by_id.get(
                task.get("concept_id")
            )

            if concept is None:
                raise RuntimeError(
                    "자동 복습 과제의 개념을 찾을 수 없습니다."
                )

            review_tasks.append(
                {
                    "task_id": task["id"],
                    "plan_id": task["plan_id"],
                    "concept_id": task["concept_id"],
                    "concept_name": concept["canonical_name"],
                    "title": task["title"],
                    "scheduled_date": task["scheduled_date"],
                    "estimated_minutes": task[
                        "estimated_minutes"
                    ],
                    "review_stage": task["review_stage"],
                    "review_interval_days": task[
                        "review_interval_days"
                    ],
                }
            )

    try:
        analysis = AdaptiveQuizAnalysis.model_validate(
            {
                "attempt_id": normalized_attempt_id,
                "mastery_changes": mastery_changes,
                "concept_masteries": concept_masteries,
                "weak_concepts": weak_concepts,
                "auto_review_tasks": review_tasks,
            }
        )
    except ValidationError as error:
        raise RuntimeError(
            "저장된 퀴즈 약점 분석 형식이 올바르지 않습니다."
        ) from error

    return analysis.model_dump(mode="json")
