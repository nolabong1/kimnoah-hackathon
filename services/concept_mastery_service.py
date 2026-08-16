from collections import defaultdict
from typing import Any


def summarize_course_masteries(
    concept_masteries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """개념 숙련도를 과목별 대시보드 요약으로 집계합니다."""

    grouped_masteries: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )

    for mastery in concept_masteries:
        course_key = mastery.get("course_key")

        if not isinstance(course_key, str) or not course_key:
            raise ValueError("과목 키가 없는 숙련도 데이터입니다.")

        grouped_masteries[course_key].append(mastery)

    course_summaries = []

    for course_key, masteries in grouped_masteries.items():
        course_names = {
            mastery["course_name"].strip()
            for mastery in masteries
            if isinstance(mastery.get("course_name"), str)
            and mastery["course_name"].strip()
        }

        if not course_names:
            raise ValueError("과목 이름이 없는 숙련도 데이터입니다.")

        scores = [mastery.get("mastery_score") for mastery in masteries]

        if any(
            not isinstance(score, int) or not 0 <= score <= 100
            for score in scores
        ):
            raise ValueError("숙련도 점수 형식이 올바르지 않습니다.")

        last_assessed_values = [
            mastery.get("last_assessed_at")
            for mastery in masteries
            if isinstance(mastery.get("last_assessed_at"), str)
            and mastery["last_assessed_at"]
        ]
        course_summaries.append(
            {
                "course_key": course_key,
                "course_name": sorted(
                    course_names,
                    key=lambda name: (name.casefold(), name),
                )[0],
                "evaluated_concept_count": len(masteries),
                "weak_concept_count": sum(
                    mastery.get("is_weak") is True
                    for mastery in masteries
                ),
                "average_mastery_score": round(
                    sum(scores) / len(scores),
                    1,
                ),
                "correct_count": sum(
                    int(mastery.get("correct_count", 0))
                    for mastery in masteries
                ),
                "incorrect_count": sum(
                    int(mastery.get("incorrect_count", 0))
                    for mastery in masteries
                ),
                "last_assessed_at": (
                    max(last_assessed_values)
                    if last_assessed_values
                    else None
                ),
            }
        )

    return sorted(
        course_summaries,
        key=lambda summary: (
            -summary["weak_concept_count"],
            summary["average_mastery_score"],
            summary["course_name"].casefold(),
        ),
    )
