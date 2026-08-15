from supabase import Client

from models.quiz import QuizDraft


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
    quiz: QuizDraft,
) -> dict:
    """객관식 퀴즈를 과제당 하나씩 저장하거나 갱신합니다."""

    questions = [
        question.model_dump()
        for question in quiz.questions
    ]
    quiz_data = {
        "user_id": user_id,
        "plan_id": plan_id,
        "task_id": task_id,
        "title": quiz.title,
        "questions": questions,
        "question_count": len(questions),
    }

    response = (
        supabase.table("quizzes")
        .upsert(
            quiz_data,
            on_conflict="task_id",
        )
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "객관식 퀴즈 저장 결과가 비어 있습니다."
        )

    return response.data[0]


def get_quiz_attempts(
    supabase: Client,
    user_id: str,
    quiz_id: str,
) -> list[dict]:
    """특정 퀴즈의 응시 기록을 최근 순서로 불러옵니다."""

    response = (
        supabase.table("quiz_attempts")
        .select(
            "id, user_id, quiz_id, attempt_number, answers, "
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

    response = (
        supabase.rpc(
            "submit_quiz_attempt",
            {
                "p_quiz_id": quiz_id,
                "p_quiz_updated_at": quiz_updated_at,
                "p_answers": answers,
            },
        )
        .execute()
    )

    if response.data is None:
        raise RuntimeError(
            "퀴즈 응시 저장 결과가 비어 있습니다."
        )

    return response.data
