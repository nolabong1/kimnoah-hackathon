from collections.abc import Iterable

from models.learning_objective import (
    LearningObjectiveConnectionReport,
    LearningObjectiveConnectionSummary,
    StoredLearningObjective,
)


def _append_title(titles: list[str], value: object) -> None:
    """표시 가능한 제목만 앞뒤 공백을 제거해 추가합니다."""

    if not isinstance(value, str):
        return
    title = value.strip()
    if title:
        titles.append(title)


def _group_titles_by_objective(
    records: Iterable[dict],
    summaries_by_id: dict[str, LearningObjectiveConnectionSummary],
    field_name: str,
) -> int:
    """레코드 제목을 목표별 목록에 넣고 미연결 레코드 수를 반환합니다."""

    unlinked_count = 0
    for record in records:
        objective_id = record.get("learning_objective_id")
        summary = summaries_by_id.get(str(objective_id))
        if summary is None:
            unlinked_count += 1
            continue
        _append_title(getattr(summary, field_name), record.get("title"))
    return unlinked_count


def _build_title_by_id(records: Iterable[dict]) -> dict[str, str]:
    """참고자료 ID로 표시 제목을 찾기 위한 안전한 사전을 만듭니다."""

    title_by_id: dict[str, str] = {}
    for record in records:
        record_id = record.get("id")
        title = record.get("title")
        if record_id is None or not isinstance(title, str) or not title.strip():
            continue
        title_by_id[str(record_id)] = title.strip()
    return title_by_id


def _group_quiz_titles(
    quizzes: Iterable[dict],
    summaries_by_id: dict[str, LearningObjectiveConnectionSummary],
    learning_material_title_by_id: dict[str, str],
    review_material_title_by_id: dict[str, str],
) -> int:
    """퀴즈 제목에 직접 선택한 참고자료 이름을 덧붙여 목표별로 묶습니다."""

    unlinked_count = 0
    for quiz in quizzes:
        summary = summaries_by_id.get(str(quiz.get("learning_objective_id")))
        if summary is None:
            unlinked_count += 1
            continue

        title = quiz.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        quiz_label = title.strip()
        reference_title = None
        learning_material_id = quiz.get("reference_learning_material_id")
        review_material_id = quiz.get("reference_review_material_id")
        if learning_material_id is not None:
            reference_title = learning_material_title_by_id.get(
                str(learning_material_id)
            )
        elif review_material_id is not None:
            reference_title = review_material_title_by_id.get(
                str(review_material_id)
            )
        if reference_title:
            quiz_label += f" · 참고: {reference_title}"
        summary.quiz_titles.append(quiz_label)
    return unlinked_count


def build_learning_objective_connection_report(
    *,
    objectives: list[StoredLearningObjective],
    tasks: list[dict],
    learning_materials: list[dict],
    review_materials: list[dict],
    quizzes: list[dict],
) -> LearningObjectiveConnectionReport:
    """계획의 목표·과제·자료·퀴즈 연결을 추가 조회 없이 집계합니다."""

    ordered_objectives = sorted(
        objectives,
        key=lambda objective: objective.sort_order,
    )
    summaries = [
        LearningObjectiveConnectionSummary(objective=objective)
        for objective in ordered_objectives
    ]
    summaries_by_id = {
        str(summary.objective.id): summary
        for summary in summaries
    }
    learning_material_title_by_id = _build_title_by_id(learning_materials)
    review_material_title_by_id = _build_title_by_id(review_materials)

    return LearningObjectiveConnectionReport(
        summaries=summaries,
        unlinked_task_count=_group_titles_by_objective(
            tasks,
            summaries_by_id,
            "task_titles",
        ),
        unlinked_source_material_count=_group_titles_by_objective(
            learning_materials,
            summaries_by_id,
            "source_material_titles",
        ),
        unlinked_review_material_count=_group_titles_by_objective(
            review_materials,
            summaries_by_id,
            "review_material_titles",
        ),
        unlinked_quiz_count=_group_quiz_titles(
            quizzes,
            summaries_by_id,
            learning_material_title_by_id,
            review_material_title_by_id,
        ),
    )
