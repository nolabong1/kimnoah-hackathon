from collections import defaultdict
from statistics import mean
from typing import Any

from models.learning_performance import (
    ConceptPerformance,
    LearningPerformanceReport,
    ObjectivePerformance,
    QuizPerformance,
    TaskTypePerformance,
)


TASK_TYPES = ("learn", "review", "quiz")
TASK_STATUSES = ("pending", "completed", "skipped")


def _required_text(value: object, field_name: str) -> str:
    """필수 문자열을 정리하고 빈 값을 거부합니다."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value.strip()


def _required_int(
    value: object,
    field_name: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    """집계에 사용하는 정수의 형식과 범위를 검증합니다."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value


def _objective_value(objective: object, field_name: str) -> object:
    """저장 목표 모델과 테스트용 dict에서 같은 필드를 읽습니다."""

    if isinstance(objective, dict):
        return objective.get(field_name)
    return getattr(objective, field_name, None)


def _average(values: list[int]) -> float | None:
    """빈 목록은 None, 나머지는 소수점 한 자리 평균으로 반환합니다."""

    return round(mean(values), 1) if values else None


def _build_quiz_performance(
    quizzes: list[dict],
    attempts: list[dict],
) -> list[QuizPerformance]:
    """퀴즈별 첫·최근·최고 점수와 응시 순서를 계산합니다."""

    attempts_by_quiz: dict[str, list[dict]] = defaultdict(list)
    quiz_ids = {
        _required_text(quiz.get("id"), "퀴즈 ID")
        for quiz in quizzes
    }
    for attempt in attempts:
        quiz_id = _required_text(attempt.get("quiz_id"), "응시 퀴즈 ID")
        if quiz_id not in quiz_ids:
            raise ValueError("선택한 계획과 연결되지 않은 퀴즈 응시가 있습니다.")
        attempts_by_quiz[quiz_id].append(attempt)

    results = []
    for quiz in quizzes:
        quiz_id = _required_text(quiz.get("id"), "퀴즈 ID")
        ordered_attempts = sorted(
            attempts_by_quiz[quiz_id],
            key=lambda attempt: (
                _required_int(
                    attempt.get("attempt_number"),
                    "응시 차수",
                    minimum=1,
                ),
                str(attempt.get("submitted_at") or ""),
            ),
        )
        score_history = [
            _required_int(
                attempt.get("score"),
                "퀴즈 점수",
                maximum=100,
            )
            for attempt in ordered_attempts
        ]
        first_score = score_history[0] if score_history else None
        latest_score = score_history[-1] if score_history else None
        results.append(
            QuizPerformance(
                quiz_id=quiz_id,
                title=_required_text(quiz.get("title"), "퀴즈 제목"),
                learning_objective_id=(
                    str(quiz["learning_objective_id"])
                    if quiz.get("learning_objective_id") is not None
                    else None
                ),
                attempt_count=len(score_history),
                first_score=first_score,
                latest_score=latest_score,
                best_score=max(score_history) if score_history else None,
                score_change=(
                    latest_score - first_score
                    if first_score is not None and latest_score is not None
                    else None
                ),
                score_history=score_history,
            )
        )
    return results


def _build_concept_performance(
    mastery_events: list[dict],
    concepts: list[dict],
    current_masteries: list[dict],
    attempts: list[dict],
) -> list[ConceptPerformance]:
    """계획 응시에서 실제 발생한 개념별 숙련도 증감을 계산합니다."""

    concept_names = {
        _required_text(concept.get("id"), "개념 ID"): _required_text(
            concept.get("canonical_name"),
            "개념 이름",
        )
        for concept in concepts
    }
    current_by_concept = {
        _required_text(mastery.get("concept_id"), "현재 숙련도 개념 ID"): mastery
        for mastery in current_masteries
    }
    attempt_order = {
        _required_text(attempt.get("id"), "응시 ID"): (
            str(attempt.get("submitted_at") or ""),
            _required_int(
                attempt.get("attempt_number"),
                "응시 차수",
                minimum=1,
            ),
        )
        for attempt in attempts
    }

    events_by_concept: dict[str, list[dict]] = defaultdict(list)
    for event in mastery_events:
        concept_id = _required_text(event.get("concept_id"), "숙련도 개념 ID")
        attempt_id = _required_text(
            event.get("quiz_attempt_id"),
            "숙련도 응시 ID",
        )
        if concept_id not in concept_names or attempt_id not in attempt_order:
            raise ValueError("숙련도 변화의 연결 정보가 올바르지 않습니다.")
        events_by_concept[concept_id].append(event)

    results = []
    for concept_id, events in events_by_concept.items():
        ordered_events = sorted(
            events,
            key=lambda event: (
                attempt_order[str(event["quiz_attempt_id"])],
                _required_int(
                    event.get("question_index"),
                    "문항 순서",
                    maximum=19,
                ),
            ),
        )
        current = current_by_concept.get(concept_id)
        current_score = None
        current_is_weak = None
        if current is not None:
            current_score = _required_int(
                current.get("mastery_score"),
                "현재 숙련도 점수",
                maximum=100,
            )
            consecutive_incorrect_count = _required_int(
                current.get("consecutive_incorrect_count"),
                "연속 오답 수",
            )
            current_is_weak = (
                current_score < 60 or consecutive_incorrect_count >= 2
            )

        correct_count = sum(
            event.get("is_correct") is True for event in ordered_events
        )
        if any(
            not isinstance(event.get("is_correct"), bool)
            for event in ordered_events
        ):
            raise ValueError("문항 정오답 정보가 올바르지 않습니다.")

        results.append(
            ConceptPerformance(
                concept_id=concept_id,
                concept_name=concept_names[concept_id],
                assessed_question_count=len(ordered_events),
                correct_count=correct_count,
                incorrect_count=len(ordered_events) - correct_count,
                first_score_before=_required_int(
                    ordered_events[0].get("score_before"),
                    "최초 숙련도 점수",
                    maximum=100,
                ),
                last_score_after=_required_int(
                    ordered_events[-1].get("score_after"),
                    "최근 숙련도 점수",
                    maximum=100,
                ),
                plan_score_delta=sum(
                    _required_int(
                        event.get("score_delta"),
                        "숙련도 증감",
                        minimum=-100,
                        maximum=100,
                    )
                    for event in ordered_events
                ),
                current_score=current_score,
                current_is_weak=current_is_weak,
            )
        )

    return sorted(
        results,
        key=lambda concept: (
            -concept.plan_score_delta,
            concept.concept_name.casefold(),
        ),
    )


def _build_objective_performance(
    objectives: list[object],
    tasks: list[dict],
    quizzes: list[QuizPerformance],
) -> tuple[list[ObjectivePerformance], int, int]:
    """세부 학습목표별 과제 완료와 최근 퀴즈 결과를 묶습니다."""

    objective_rows = []
    objective_ids = set()
    for objective in objectives:
        objective_id = _required_text(
            _objective_value(objective, "id"),
            "학습목표 ID",
        )
        objective_ids.add(objective_id)
        objective_rows.append(
            (
                _required_int(
                    _objective_value(objective, "sort_order"),
                    "학습목표 순서",
                ),
                objective_id,
                _required_text(
                    _objective_value(objective, "title"),
                    "학습목표 제목",
                ),
            )
        )

    tasks_by_objective: dict[str, list[dict]] = defaultdict(list)
    unlinked_task_count = 0
    for task in tasks:
        objective_id = task.get("learning_objective_id")
        if objective_id is None or str(objective_id) not in objective_ids:
            unlinked_task_count += 1
            continue
        tasks_by_objective[str(objective_id)].append(task)

    quizzes_by_objective: dict[str, list[QuizPerformance]] = defaultdict(list)
    unlinked_quiz_count = 0
    for quiz in quizzes:
        objective_id = quiz.learning_objective_id
        if objective_id is None or objective_id not in objective_ids:
            unlinked_quiz_count += 1
            continue
        quizzes_by_objective[objective_id].append(quiz)

    results = []
    for _, objective_id, title in sorted(objective_rows):
        objective_tasks = tasks_by_objective[objective_id]
        completed_tasks = sum(
            task.get("status") == "completed" for task in objective_tasks
        )
        objective_quizzes = quizzes_by_objective[objective_id]
        latest_scores = [
            quiz.latest_score
            for quiz in objective_quizzes
            if quiz.latest_score is not None
        ]
        results.append(
            ObjectivePerformance(
                learning_objective_id=objective_id,
                title=title,
                task_count=len(objective_tasks),
                completed_task_count=completed_tasks,
                completion_rate=(
                    round(completed_tasks / len(objective_tasks) * 100, 1)
                    if objective_tasks
                    else 0.0
                ),
                quiz_count=len(objective_quizzes),
                attempted_quiz_count=len(latest_scores),
                latest_quiz_average=_average(latest_scores),
            )
        )
    return results, unlinked_task_count, unlinked_quiz_count


def build_learning_performance_report(data: dict[str, Any]) -> LearningPerformanceReport:
    """조회된 기록으로 결정론적인 계획별 학습성과 리포트를 만듭니다."""

    plan = data.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("학습계획 정보가 올바르지 않습니다.")
    tasks = list(data.get("tasks") or [])
    objectives = list(data.get("objectives") or [])
    quizzes = list(data.get("quizzes") or [])
    attempts = list(data.get("attempts") or [])
    mastery_events = list(data.get("mastery_events") or [])
    concepts = list(data.get("concepts") or [])
    current_masteries = list(data.get("current_masteries") or [])

    status_counts = {status: 0 for status in TASK_STATUSES}
    task_type_counts = {
        task_type: {"total": 0, "completed": 0}
        for task_type in TASK_TYPES
    }
    total_planned_minutes = 0
    completed_estimated_minutes = 0
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("학습과제 정보가 올바르지 않습니다.")
        status = task.get("status")
        task_type = task.get("task_type")
        if status not in status_counts or task_type not in task_type_counts:
            raise ValueError("학습과제 상태 또는 유형이 올바르지 않습니다.")
        estimated_minutes = _required_int(
            task.get("estimated_minutes"),
            "과제 예상 학습시간",
            minimum=1,
            maximum=1440,
        )
        status_counts[status] += 1
        task_type_counts[task_type]["total"] += 1
        total_planned_minutes += estimated_minutes
        if status == "completed":
            task_type_counts[task_type]["completed"] += 1
            completed_estimated_minutes += estimated_minutes

    quiz_performance = _build_quiz_performance(quizzes, attempts)
    attempted_quizzes = [
        quiz for quiz in quiz_performance if quiz.attempt_count > 0
    ]
    concept_performance = _build_concept_performance(
        mastery_events,
        concepts,
        current_masteries,
        attempts,
    )
    objective_performance, unlinked_tasks, unlinked_quizzes = (
        _build_objective_performance(
            objectives,
            tasks,
            quiz_performance,
        )
    )

    total_tasks = len(tasks)
    first_scores = [
        quiz.first_score
        for quiz in attempted_quizzes
        if quiz.first_score is not None
    ]
    latest_scores = [
        quiz.latest_score
        for quiz in attempted_quizzes
        if quiz.latest_score is not None
    ]
    best_scores = [
        quiz.best_score
        for quiz in attempted_quizzes
        if quiz.best_score is not None
    ]
    score_changes = [
        quiz.score_change
        for quiz in attempted_quizzes
        if quiz.score_change is not None
    ]

    return LearningPerformanceReport(
        plan_id=_required_text(plan.get("id"), "학습계획 ID"),
        plan_title=_required_text(plan.get("title"), "학습계획 제목"),
        course_name=_required_text(plan.get("course_name"), "과목 이름"),
        plan_start_date=plan.get("start_date"),
        plan_target_date=plan.get("target_date"),
        total_tasks=total_tasks,
        completed_tasks=status_counts["completed"],
        pending_tasks=status_counts["pending"],
        skipped_tasks=status_counts["skipped"],
        completion_rate=(
            round(status_counts["completed"] / total_tasks * 100, 1)
            if total_tasks
            else 0.0
        ),
        total_planned_minutes=total_planned_minutes,
        completed_estimated_minutes=completed_estimated_minutes,
        task_type_performance=[
            TaskTypePerformance(
                task_type=task_type,
                total_tasks=task_type_counts[task_type]["total"],
                completed_tasks=task_type_counts[task_type]["completed"],
            )
            for task_type in TASK_TYPES
        ],
        quiz_count=len(quiz_performance),
        attempted_quiz_count=len(attempted_quizzes),
        total_quiz_attempts=sum(
            quiz.attempt_count for quiz in quiz_performance
        ),
        average_first_score=_average(first_scores),
        average_latest_score=_average(latest_scores),
        average_best_score=_average(best_scores),
        average_score_change=_average(score_changes),
        evaluated_concept_count=len(concept_performance),
        improved_concept_count=sum(
            concept.plan_score_delta > 0 for concept in concept_performance
        ),
        plan_mastery_score_delta=sum(
            concept.plan_score_delta for concept in concept_performance
        ),
        quizzes=quiz_performance,
        concepts=concept_performance,
        objectives=objective_performance,
        unlinked_task_count=unlinked_tasks,
        unlinked_quiz_count=unlinked_quizzes,
    )


def build_performance_highlights(
    report: LearningPerformanceReport,
) -> list[str]:
    """리포트 상단에 표시할 근거 기반 핵심 문장을 만듭니다."""

    highlights = [
        f"전체 {report.total_tasks}개 과제 중 {report.completed_tasks}개를 "
        f"완료해 완료율 {report.completion_rate:g}%를 기록했습니다."
    ]
    if report.average_latest_score is None:
        highlights.append("아직 비교할 수 있는 퀴즈 응시 기록이 없습니다.")
    else:
        change = report.average_score_change or 0.0
        direction = "상승" if change > 0 else "하락" if change < 0 else "유지"
        highlights.append(
            f"응시한 퀴즈의 최근 평균은 {report.average_latest_score:g}점이며, "
            f"첫 응시 평균보다 {abs(change):g}점 {direction}했습니다."
        )
    if report.evaluated_concept_count:
        highlights.append(
            f"{report.evaluated_concept_count}개 개념을 평가했고, 이 계획의 "
            f"문항으로 {report.improved_concept_count}개 개념에서 양의 숙련도 "
            "변화가 확인됐습니다."
        )
    else:
        highlights.append("개념 숙련도 변화를 확인할 퀴즈 기록이 아직 없습니다.")
    return highlights
