from typing import Any

from models.learner_context import (
    LearnerConceptContext,
    LearnerContext,
)
from services.concept_mastery_repository import (
    get_course_concept_masteries,
)
from services.concept_service import normalize_course_key


MAX_FOCUS_CONCEPTS = 6
MAX_STABLE_CONCEPTS = 3
WEAK_MASTERY_THRESHOLD = 60
STABLE_MASTERY_THRESHOLD = 80


def load_learner_context(
    supabase,
    user_id: str,
    course_name: str,
    course_key: str | None = None,
) -> LearnerContext | None:
    """본인의 과목 숙련도를 조회해 제한된 AI 문맥으로 조립합니다."""

    normalized_course_key = (
        normalize_course_key(course_name)
        if course_key is None
        else course_key.strip()
    )
    if not normalized_course_key:
        raise ValueError("학습자 문맥의 과목 키가 필요합니다.")
    masteries = get_course_concept_masteries(
        supabase=supabase,
        user_id=user_id,
        course_key=normalized_course_key,
    )
    return build_learner_context(normalized_course_key, masteries)


def build_learner_context(
    course_key: str,
    masteries: list[dict[str, Any]],
) -> LearnerContext | None:
    """숙련도 행을 우선 개념과 안정 개념으로 결정론적으로 축약합니다."""

    normalized_course_key = course_key.strip()
    if not normalized_course_key:
        raise ValueError("학습자 문맥의 과목 키가 필요합니다.")
    if not masteries:
        return None

    concepts = [_parse_mastery_row(row) for row in masteries]
    focus_candidates = [
        concept
        for concept in concepts
        if concept.is_weak
        or concept.recent_result == "incorrect"
        or concept.mastery_score < WEAK_MASTERY_THRESHOLD
    ]
    focus_candidates.sort(
        key=lambda concept: (
            not concept.is_weak,
            concept.recent_result != "incorrect",
            -concept.consecutive_incorrect_count,
            concept.mastery_score,
            -concept.incorrect_count,
            concept.concept_name.casefold(),
        )
    )
    focus_concepts = focus_candidates[:MAX_FOCUS_CONCEPTS]
    focus_keys = {concept.concept_key for concept in focus_concepts}

    stable_candidates = [
        concept
        for concept in concepts
        if concept.concept_key not in focus_keys
        and not concept.is_weak
        and concept.recent_result != "incorrect"
        and concept.mastery_score >= STABLE_MASTERY_THRESHOLD
    ]
    stable_candidates.sort(
        key=lambda concept: (
            -concept.mastery_score,
            -concept.correct_count,
            concept.concept_name.casefold(),
        )
    )

    return LearnerContext(
        course_key=normalized_course_key,
        evaluated_concept_count=len(concepts),
        weak_concept_count=sum(concept.is_weak for concept in concepts),
        average_mastery_score=round(
            sum(concept.mastery_score for concept in concepts) / len(concepts),
            1,
        ),
        focus_concepts=focus_concepts,
        stable_concepts=stable_candidates[:MAX_STABLE_CONCEPTS],
    )


def learner_context_to_prompt_payload(
    context: LearnerContext | dict | None,
) -> dict[str, Any] | None:
    """허용된 학습 신호만 AI 요청용 JSON 객체로 변환합니다."""

    if context is None:
        return None
    normalized = (
        context
        if isinstance(context, LearnerContext)
        else LearnerContext.model_validate(context)
    )
    return normalized.model_dump(mode="json")


def _parse_mastery_row(row: dict[str, Any]) -> LearnerConceptContext:
    """저장소 행에서 사용자·DB 식별자를 제외한 개념 신호만 검증합니다."""

    if not isinstance(row, dict):
        raise ValueError("개념 숙련도 행 형식이 올바르지 않습니다.")
    last_answer_correct = row.get("last_answer_correct")
    if last_answer_correct is not None and not isinstance(
        last_answer_correct,
        bool,
    ):
        raise ValueError("최근 정오답 신호 형식이 올바르지 않습니다.")
    is_weak = row.get("is_weak", False)
    if not isinstance(is_weak, bool):
        raise ValueError("취약 개념 신호 형식이 올바르지 않습니다.")
    if last_answer_correct is True:
        recent_result = "correct"
    elif last_answer_correct is False:
        recent_result = "incorrect"
    else:
        recent_result = "unknown"

    return LearnerConceptContext.model_validate(
        {
            "concept_key": row.get("concept_key"),
            "concept_name": row.get("concept_name"),
            "mastery_score": row.get("mastery_score"),
            "correct_count": row.get("correct_count"),
            "incorrect_count": row.get("incorrect_count"),
            "consecutive_incorrect_count": row.get(
                "consecutive_incorrect_count"
            ),
            "recent_result": recent_result,
            "is_weak": is_weak,
        }
    )
