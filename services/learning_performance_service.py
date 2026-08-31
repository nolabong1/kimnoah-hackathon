from collections import defaultdict
from html import escape
import re
from statistics import mean
from typing import Any
from uuid import UUID

from models.learning_performance import (
    ConceptPerformance,
    LearningPerformanceReport,
    ObjectivePerformance,
    QuizPerformance,
    TaskTypePerformance,
)
from services.weekly_review_service import REFLECTION_QUESTIONS


TASK_TYPES = ("learn", "review", "quiz")
TASK_STATUSES = ("pending", "completed", "skipped")
TASK_TYPE_LABELS = {
    "learn": "학습",
    "review": "복습",
    "quiz": "퀴즈",
}


def _required_text(value: object, field_name: str) -> str:
    """필수 문자열을 정리하고 빈 값을 거부합니다."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value.strip()


def _required_identifier(value: object, field_name: str) -> str:
    """문자열 또는 Pydantic이 변환한 UUID를 문자열 ID로 정규화합니다."""

    if isinstance(value, UUID):
        return str(value)
    return _required_text(value, field_name)


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
        objective_id = _required_identifier(
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


def summarize_before_after_evidence(
    report: LearningPerformanceReport,
) -> dict[str, int]:
    """계획 안에서 확인된 개념 숙련도 전후 비교 수를 계산합니다."""

    return {
        "evaluated_concept_count": len(report.concepts),
        "improved_concept_count": sum(
            concept.last_score_after > concept.first_score_before
            for concept in report.concepts
        ),
        "score_threshold_reached_count": sum(
            concept.first_score_before < 60 <= concept.last_score_after
            for concept in report.concepts
        ),
    }


def _html_text(value: object) -> str:
    """동적 값을 실행되지 않는 HTML 텍스트로 바꿉니다."""

    return escape(str(value), quote=True)


def _html_multiline(value: object) -> str:
    """동적 여러 줄 텍스트를 안전한 줄바꿈과 함께 표시합니다."""

    normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return _html_text(normalized).replace("\n", "<br>")


def _html_inline_markdown(value: object) -> str:
    """이스케이프 후 저장된 회고의 굵은 글씨만 제한적으로 변환합니다."""

    safe_text = _html_text(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe_text)


def _score_text(value: float | int | None) -> str:
    """선택적인 점수를 보고서용 문자열로 바꿉니다."""

    return "기록 없음" if value is None else f"{value:g}점"


def _score_delta_text(value: float | int | None) -> str:
    """선택적인 점수 변화를 부호가 있는 문자열로 바꿉니다."""

    return "기록 없음" if value is None else f"{value:+g}점"


def _build_html_table(headers: list[str], rows: list[list[object]]) -> str:
    """읽기 전용 데이터를 반응형 HTML 표로 변환합니다."""

    header_html = "".join(f"<th>{_html_text(header)}</th>" for header in headers)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{_html_text(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        f"{header_html}</tr></thead><tbody>{row_html}</tbody></table></div>"
    )


def _saved_markdown_to_safe_html(markdown: str | None) -> str:
    """저장된 고정 회고 Markdown의 제목·목록·문단만 안전하게 표시합니다."""

    if not isinstance(markdown, str) or not markdown.strip():
        return '<p class="empty">저장된 AI 주간 회고가 없습니다.</p>'

    parts: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        if not list_items:
            return
        parts.append(
            "<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>"
        )
        list_items.clear()

    for raw_line in markdown.strip().splitlines():
        line = raw_line.strip()
        if not line:
            flush_list()
            continue
        if line.startswith("### "):
            flush_list()
            parts.append(f"<h3>{_html_inline_markdown(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_list()
            parts.append(f"<h3>{_html_inline_markdown(line[3:])}</h3>")
        elif line.startswith("- "):
            list_items.append(_html_inline_markdown(line[2:]))
        else:
            flush_list()
            parts.append(f"<p>{_html_inline_markdown(line)}</p>")
    flush_list()
    return "".join(parts)


def build_learning_performance_html(
    report: LearningPerformanceReport,
    *,
    reflection_answers: dict[str, object] | None = None,
    ai_review_markdown: str | None = None,
) -> str:
    """저장된 성과와 회고를 재호출 없이 독립 HTML 문서로 변환합니다."""

    task_table = _build_html_table(
        ["과제 유형", "계획", "완료"],
        [
            [
                TASK_TYPE_LABELS[item.task_type],
                f"{item.total_tasks}개",
                f"{item.completed_tasks}개",
            ]
            for item in report.task_type_performance
        ],
    )

    attempted_quizzes = [
        quiz for quiz in report.quizzes if quiz.attempt_count > 0
    ]
    if attempted_quizzes:
        quiz_section = _build_html_table(
            ["퀴즈", "응시", "첫 점수", "최근 점수", "최고 점수", "변화"],
            [
                [
                    quiz.title,
                    f"{quiz.attempt_count}회",
                    _score_text(quiz.first_score),
                    _score_text(quiz.latest_score),
                    _score_text(quiz.best_score),
                    _score_delta_text(quiz.score_change),
                ]
                for quiz in attempted_quizzes
            ],
        )
    else:
        quiz_section = '<p class="empty">퀴즈 응시 기록이 없습니다.</p>'

    if report.concepts:
        concept_section = _build_html_table(
            [
                "개념",
                "평가 문항",
                "정답",
                "오답",
                "첫 평가 직전",
                "마지막 평가 직후",
                "계획 문항 증감",
                "현재 숙련도",
            ],
            [
                [
                    concept.concept_name,
                    f"{concept.assessed_question_count}개",
                    f"{concept.correct_count}개",
                    f"{concept.incorrect_count}개",
                    _score_text(concept.first_score_before),
                    _score_text(concept.last_score_after),
                    _score_delta_text(concept.plan_score_delta),
                    _score_text(concept.current_score),
                ]
                for concept in report.concepts
            ],
        )
    else:
        concept_section = '<p class="empty">개념 숙련도 평가 기록이 없습니다.</p>'

    if report.objectives:
        objective_parts = []
        for index, objective in enumerate(report.objectives, start=1):
            objective_parts.append(
                '<article class="objective-card">'
                f"<h3>{index}. {_html_text(objective.title)}</h3>"
                "<ul>"
                f"<li>과제 완료: {objective.completed_task_count}/"
                f"{objective.task_count}개 ({objective.completion_rate:g}%)</li>"
                f"<li>퀴즈 응시: {objective.attempted_quiz_count}/"
                f"{objective.quiz_count}개</li>"
                f"<li>최근 퀴즈 평균: {_score_text(objective.latest_quiz_average)}</li>"
                "</ul></article>"
            )
        objective_section = '<div class="objective-grid">' + "".join(
            objective_parts
        ) + "</div>"
    else:
        objective_section = '<p class="empty">연결된 세부 학습목표가 없습니다.</p>'

    cleaned_reflections = []
    reflection_answers = reflection_answers or {}
    for key, question in REFLECTION_QUESTIONS.items():
        answer = str(reflection_answers.get(key, "")).strip()
        if not answer:
            continue
        cleaned_reflections.append(
            '<article class="reflection-card">'
            f"<h3>{_html_text(question)}</h3>"
            f"<p>{_html_multiline(answer)}</p>"
            "</article>"
        )
    reflection_section = (
        "".join(cleaned_reflections)
        if cleaned_reflections
        else '<p class="empty">저장된 직접 회고 답변이 없습니다.</p>'
    )

    highlights = "".join(
        f"<li>{_html_text(highlight)}</li>"
        for highlight in build_performance_highlights(report)
    )
    summary = summarize_before_after_evidence(report)
    document_head = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>학습 성과 리포트</title>
  <style>
    :root { --primary:#5B4FE5; --ink:#172033; --muted:#687086;
      --line:#E3E6EF; --surface:#FFFFFF; --soft:#F5F6FC; }
    * { box-sizing:border-box; }
    body { margin:0; background:#EEF0F7; color:var(--ink);
      font-family:Pretendard,"Noto Sans KR","Malgun Gothic",sans-serif;
      line-height:1.65; }
    .report { max-width:1040px; margin:32px auto; padding:48px;
      background:var(--surface); border-radius:20px;
      box-shadow:0 16px 48px rgba(35,42,78,.10); }
    header { padding:28px; border-radius:16px;
      background:linear-gradient(135deg,#F0EEFF,#F7F8FF); }
    h1 { margin:0 0 8px; font-size:32px; letter-spacing:-.04em; }
    h2 { margin:40px 0 16px; font-size:22px; letter-spacing:-.025em; }
    h3 { margin:0 0 10px; font-size:16px; }
    p { margin:8px 0; }
    .meta { color:var(--muted); margin:4px 0; }
    .metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
      gap:12px; margin-top:20px; }
    .metric { padding:18px; border:1px solid var(--line); border-radius:14px;
      background:var(--surface); }
    .metric span { display:block; color:var(--muted); font-size:13px; }
    .metric strong { display:block; margin-top:6px; font-size:24px; }
    .evidence { padding:18px 22px; border-left:4px solid var(--primary);
      border-radius:0 12px 12px 0; background:var(--soft); }
    .evidence ul, .objective-card ul { margin:0; padding-left:20px; }
    .table-wrap { overflow-x:auto; border:1px solid var(--line);
      border-radius:12px; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th, td { padding:12px 14px; text-align:left; border-bottom:1px solid var(--line);
      white-space:nowrap; }
    th { background:var(--soft); color:#4E5670; font-weight:700; }
    tbody tr:last-child td { border-bottom:0; }
    .objective-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
      gap:12px; }
    .objective-card, .reflection-card, .ai-review { padding:20px;
      border:1px solid var(--line); border-radius:14px; break-inside:avoid; }
    .reflection-card { margin-bottom:12px; }
    .reflection-card p { color:#3E465D; }
    .ai-review h3 { margin-top:24px; color:var(--primary); }
    .ai-review h3:first-child { margin-top:0; }
    .empty { padding:18px; color:var(--muted); border:1px dashed var(--line);
      border-radius:12px; background:var(--soft); }
    footer { margin-top:40px; padding-top:18px; border-top:1px solid var(--line);
      color:var(--muted); font-size:13px; }
    @media (max-width:760px) { .report { margin:0; padding:24px; border-radius:0; }
      .metrics, .objective-grid { grid-template-columns:1fr 1fr; } }
    @media print { @page { size:A4; margin:14mm; } body { background:#fff; }
      .report { max-width:none; margin:0; padding:0; box-shadow:none; }
      header { print-color-adjust:exact; -webkit-print-color-adjust:exact; }
      h2, .metric, .objective-card, .reflection-card { break-inside:avoid; }
      table { font-size:10px; } th, td { padding:7px; } }
  </style>
</head>
<body>
"""
    document_body = f"""
<main class="report">
  <header>
    <h1>학습 성과 리포트</h1>
    <p class="meta"><strong>계획</strong> · {_html_text(report.plan_title)}</p>
    <p class="meta"><strong>과목</strong> · {_html_text(report.course_name)}</p>
    <p class="meta"><strong>기간</strong> · {report.plan_start_date.isoformat()} ~ {report.plan_target_date.isoformat()}</p>
    <div class="metrics">
      <div class="metric"><span>과제 완료율</span><strong>{report.completion_rate:g}%</strong></div>
      <div class="metric"><span>완료 과제 기준 예상 학습량</span><strong>{report.completed_estimated_minutes}분</strong></div>
      <div class="metric"><span>첫 퀴즈 응시 평균</span><strong>{_score_text(report.average_first_score)}</strong></div>
      <div class="metric"><span>최근 퀴즈 응시 평균</span><strong>{_score_text(report.average_latest_score)}</strong></div>
    </div>
  </header>
  <h2>핵심 성과</h2>
  <div class="evidence"><ul>{highlights}</ul></div>
  <div class="metrics">
    <div class="metric"><span>숙련도 상승 개념</span><strong>{summary['improved_concept_count']}/{summary['evaluated_concept_count']}개</strong></div>
    <div class="metric"><span>60점 기준 신규 도달</span><strong>{summary['score_threshold_reached_count']}개</strong></div>
    <div class="metric"><span>퀴즈 총 응시</span><strong>{report.total_quiz_attempts}회</strong></div>
    <div class="metric"><span>첫 응시 대비 평균 변화</span><strong>{_score_delta_text(report.average_score_change)}</strong></div>
  </div>
  <h2>과제 유형별 실행</h2>{task_table}
  <h2>학습목표별 근거</h2>{objective_section}
  <h2>퀴즈 점수 변화</h2>{quiz_section}
  <h2>개념별 숙련도 근거</h2>{concept_section}
  <h2>학생이 직접 작성한 회고</h2>{reflection_section}
  <h2>AI 주간 회고 분석</h2>
  <div class="ai-review">{_saved_markdown_to_safe_html(ai_review_markdown)}</div>
  <footer>이 보고서는 저장된 과제·퀴즈·숙련도·주간 회고 기록을 요약합니다.
    완료 과제 기준 예상 학습량은 실제 측정 시간이 아니며, 점수 변화만으로
    학습 효과의 인과관계를 단정하지 않습니다. 브라우저의 인쇄 기능을 사용하면
    PDF로 저장할 수 있습니다.</footer>
</main>
</body>
</html>
"""
    return document_head + document_body
