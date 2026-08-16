from uuid import UUID

from pydantic import ValidationError
from supabase import Client

from models.concept_mastery import AdaptiveQuizAnalysis
from models.quiz import QuizDraft
from services.concept_service import build_quiz_concept_payload


def get_learning_concept_catalog(
    supabase: Client,
    user_id: str,
    course_key: str,
) -> list[dict]:
    """사용자와 과목에 속한 기존 정규 개념과 별칭을 조회합니다."""

    concepts_response = (
        supabase.table("learning_concepts")
        .select(
            "id, concept_key, canonical_name, updated_at"
        )
        .eq("user_id", user_id)
        .eq("course_key", course_key)
        .order("updated_at", desc=True)
        .limit(100)
        .execute()
    )
    concepts = concepts_response.data or []

    if not concepts:
        return []

    aliases_response = (
        supabase.table("concept_aliases")
        .select(
            "concept_id, alias_name, normalized_alias"
        )
        .eq("user_id", user_id)
        .eq("course_key", course_key)
        .limit(500)
        .execute()
    )
    aliases_by_concept: dict[str, list[str]] = {}

    for alias in aliases_response.data or []:
        concept_id = alias.get("concept_id")
        alias_name = alias.get("alias_name")

        if (
            not isinstance(concept_id, str)
            or not isinstance(alias_name, str)
        ):
            continue

        aliases_by_concept.setdefault(
            concept_id,
            [],
        ).append(alias_name)

    return [
        {
            "concept_key": concept["concept_key"],
            "concept_name": concept["canonical_name"],
            "aliases": aliases_by_concept.get(
                concept["id"],
                [],
            ),
        }
        for concept in concepts
    ]


def get_quiz_by_task(
    supabase: Client,
    user_id: str,
    task_id: str,
) -> dict | None:
    """특정 과제에 저장된 객관식 퀴즈를 불러옵니다."""

    response = (
        supabase.table("quizzes")
        .select(
            "id, user_id, plan_id, task_id, title, "
            "questions, question_count, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("task_id", task_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def save_quiz(
    supabase: Client,
    user_id: str,
    plan_id: str,
    task_id: str,
    course_key: str,
    course_name: str,
    quiz: QuizDraft,
) -> dict:
    """개념 사전과 객관식 퀴즈를 서버에서 원자적으로 저장합니다."""

    questions = [
        question.model_dump()
        for question in quiz.questions
    ]
    concepts = build_quiz_concept_payload(quiz)

    response = (
        supabase.rpc(
            "save_quiz_with_concepts",
            {
                "p_plan_id": plan_id,
                "p_task_id": task_id,
                "p_course_key": course_key,
                "p_course_name": course_name,
                "p_title": quiz.title,
                "p_questions": questions,
                "p_concepts": concepts,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError(
            "객관식 퀴즈 저장 결과가 비어 있습니다."
        )

    if response.data.get("user_id") != user_id:
        raise RuntimeError(
            "저장된 퀴즈의 사용자 정보가 올바르지 않습니다."
        )

    return response.data


def get_quiz_attempts(
    supabase: Client,
    user_id: str,
    quiz_id: str,
) -> list[dict]:
    """특정 퀴즈의 응시 기록을 최근 순서로 불러옵니다."""

    response = (
        supabase.table("quiz_attempts")
        .select(
            "id, user_id, quiz_id, submission_key, "
            "attempt_number, answers, "
            "questions_snapshot, quiz_updated_at, correct_count, "
            "total_questions, score, exp_awarded, submitted_at"
        )
        .eq("user_id", user_id)
        .eq("quiz_id", quiz_id)
        .order("attempt_number", desc=True)
        .execute()
    )

    return response.data or []


def submit_quiz_attempt(
    supabase: Client,
    quiz_id: str,
    quiz_updated_at: str,
    answers: list[int],
    submission_key: str,
) -> dict:
    """서버 채점 RPC를 호출해 퀴즈 응시 기록을 저장합니다."""

    if (
        not isinstance(quiz_id, str)
        or not quiz_id.strip()
    ):
        raise ValueError("퀴즈 ID가 필요합니다.")

    if (
        not isinstance(quiz_updated_at, str)
        or not quiz_updated_at.strip()
    ):
        raise ValueError("퀴즈 버전 정보가 필요합니다.")

    if (
        not isinstance(answers, list)
        or not 1 <= len(answers) <= 20
    ):
        raise ValueError(
            "퀴즈 답안은 1개 이상 20개 이하여야 합니다."
        )

    if any(
        isinstance(answer, bool)
        or not isinstance(answer, int)
        or answer not in range(4)
        for answer in answers
    ):
        raise ValueError(
            "각 답안은 0부터 3 사이의 정수여야 합니다."
        )

    try:
        normalized_submission_key = str(
            UUID(submission_key)
        )
    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            "퀴즈 제출 식별 키 형식이 올바르지 않습니다."
        ) from None

    response = (
        supabase.rpc(
            "submit_quiz_attempt",
            {
                "p_quiz_id": quiz_id,
                "p_quiz_updated_at": quiz_updated_at,
                "p_answers": answers,
                "p_submission_key": normalized_submission_key,
            },
        )
        .execute()
    )

    if not isinstance(response.data, dict):
        raise RuntimeError(
            "퀴즈 응시 저장 결과가 비어 있습니다."
        )

    try:
        analysis = AdaptiveQuizAnalysis.model_validate(
            response.data
        )
    except ValidationError as error:
        raise RuntimeError(
            "퀴즈 약점 분석 결과 형식이 올바르지 않습니다."
        ) from error

    normalized_result = dict(response.data)
    normalized_result.update(
        analysis.model_dump(mode="json")
    )

    return normalized_result
