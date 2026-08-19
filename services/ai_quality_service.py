import json
import unicodedata
from pathlib import Path

from pydantic import TypeAdapter

from models.ai_quality import (
    AIQualityCase,
    AIQualityCheck,
    AIQualityFeature,
    AIQualityReport,
    AIQualitySeverity,
)
from models.quiz import QuizDraft
from models.review_material import ReviewMaterialDraft
from models.study_plan import WeeklyStudyPlan
from models.tutor import TutorGuidance
from services.review_material_service import REQUIRED_SECTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "ai_quality_cases.json"
)
QUALITY_CASES_ADAPTER = TypeAdapter(list[AIQualityCase])
DISALLOWED_QUIZ_CHOICES = (
    "모두 정답",
    "정답 없음",
    "알 수 없음",
)


def load_ai_quality_cases(
    path: Path = DEFAULT_CASES_PATH,
) -> list[AIQualityCase]:
    """버전 관리되는 대표 평가 사례를 JSON에서 불러옵니다."""

    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = QUALITY_CASES_ADAPTER.validate_python(raw_cases)
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("AI 품질 평가 사례 ID는 서로 달라야 합니다.")
    return cases


def evaluate_review_material_quality(
    case: AIQualityCase,
    material: ReviewMaterialDraft,
) -> AIQualityReport:
    """학습자료의 구성·근거 표현·기대 개념 포함 여부를 검사합니다."""

    _require_feature(case, "review_material")
    markdown = material.content_markdown
    section_positions = [
        markdown.find(section) for section in REQUIRED_SECTIONS
    ]
    checks = [
        _check(
            "required_sections_once",
            all(markdown.count(section) == 1 for section in REQUIRED_SECTIONS),
            "error",
            "필수 학습자료 섹션이 각각 정확히 한 번 포함되어야 합니다.",
        ),
        _check(
            "required_sections_ordered",
            section_positions == sorted(section_positions)
            and all(position >= 0 for position in section_positions),
            "error",
            "필수 학습자료 섹션이 승인된 순서로 배치되어야 합니다.",
        ),
        _check(
            "required_sections_nonempty",
            _sections_are_nonempty(markdown, REQUIRED_SECTIONS),
            "error",
            "각 학습자료 섹션에 실제 학습 내용이 있어야 합니다.",
        ),
    ]
    checks.extend(
        _text_expectation_checks(case, f"{material.title}\n{markdown}")
    )
    return _report(case, checks)


def evaluate_quiz_quality(
    case: AIQualityCase,
    quiz: QuizDraft,
) -> AIQualityReport:
    """퀴즈의 금지 선택지·개념 범위·해설 기본 품질을 검사합니다."""

    _require_feature(case, "quiz")
    choices = [
        choice
        for question in quiz.questions
        for choice in question.choices
    ]
    concept_keys = {question.concept_key for question in quiz.questions}
    evidence_keys = [question.evidence_key for question in quiz.questions]
    explanations_are_distinct = all(
        _normalize(question.explanation)
        != _normalize(question.choices[question.correct_answer_index])
        for question in quiz.questions
    )
    checks = [
        _check(
            "disallowed_choices_absent",
            not any(
                _contains_normalized(choice, disallowed)
                for choice in choices
                for disallowed in DISALLOWED_QUIZ_CHOICES
            ),
            "error",
            "모두 정답·정답 없음과 같은 진단 가치가 낮은 선택지를 사용하지 않습니다.",
        ),
        _check(
            "expected_concepts_covered",
            set(case.expected_concept_keys).issubset(concept_keys),
            "error",
            "평가 사례에서 요구한 대표 개념이 퀴즈에 포함되어야 합니다.",
        ),
        _check(
            "blueprint_evidence_distribution",
            evidence_keys.count("explain") == 2
            and evidence_keys.count("apply") == 2
            and evidence_keys.count("differentiate") == 1,
            "error",
            (
                "퀴즈는 공통 학습 설계도의 설명 2·적용 2·"
                "오해 구분 1 기준을 평가해야 합니다."
            ),
        ),
        _check(
            "explanations_add_reasoning",
            explanations_are_distinct,
            "warning",
            "해설은 정답 선택지를 그대로 반복하지 않고 근거를 설명해야 합니다.",
        ),
    ]
    combined_text = "\n".join(
        [
            quiz.title,
            *(
                text
                for question in quiz.questions
                for text in (
                    question.question,
                    *question.choices,
                    question.explanation,
                    question.concept_name,
                )
            ),
        ]
    )
    checks.extend(_text_expectation_checks(case, combined_text))
    return _report(case, checks)


def evaluate_tutor_quality(
    case: AIQualityCase,
    guidance: TutorGuidance,
) -> AIQualityReport:
    """튜터 힌트의 정답 비공개와 단계적 구체화를 검사합니다."""

    _require_feature(case, "tutor")
    hint_texts = [
        f"{hint.title}\n{hint.content}\n{hint.guiding_question}"
        for hint in guidance.hints
    ]
    normalized_answer = _normalize(guidance.final_solution.final_answer)
    answer_can_be_compared = len(normalized_answer) >= 3
    answer_is_hidden = not answer_can_be_compared or all(
        normalized_answer not in _normalize(hint_text)
        for hint_text in hint_texts
    )
    hint_lengths = [len(_normalize(hint.content)) for hint in guidance.hints]
    checks = [
        _check(
            "final_answer_hidden_in_hints",
            answer_is_hidden,
            "error",
            "세 단계 힌트에는 최종 정답 문자열이 직접 노출되지 않아야 합니다.",
        ),
        _check(
            "hint_detail_progression",
            hint_lengths[0] <= hint_lengths[2],
            "warning",
            "Hint 3은 Hint 1보다 구체적인 해결 발판을 제공해야 합니다.",
        ),
    ]
    combined_text = "\n".join(
        [
            guidance.problem_summary,
            *guidance.required_concepts,
            *hint_texts,
            guidance.final_solution.final_answer,
            *guidance.final_solution.reasoning_steps,
            guidance.final_solution.why_solution_works,
        ]
    )
    checks.extend(_text_expectation_checks(case, combined_text))
    return _report(case, checks)


def evaluate_study_plan_quality(
    case: AIQualityCase,
    plan: WeeklyStudyPlan,
    available_schedule: dict[str, int],
) -> AIQualityReport:
    """7일 계획의 일정·시간·학습 활동 구성을 검사합니다."""

    _require_feature(case, "study_plan")
    offsets = [day.day_offset for day in plan.days]
    daily_limits_are_valid = all(
        f"{day.day_offset}일차" in available_schedule
        and sum(task.estimated_minutes for task in day.tasks)
        <= available_schedule[f"{day.day_offset}일차"]
        for day in plan.days
    )
    task_types = {
        task.task_type
        for day in plan.days
        for task in day.tasks
    }
    checks = [
        _check(
            "seven_days_ordered",
            offsets == list(range(7)),
            "error",
            "계획은 day_offset 0부터 6까지 정확히 한 번씩 포함해야 합니다.",
        ),
        _check(
            "daily_time_limits_respected",
            daily_limits_are_valid,
            "error",
            "각 날짜의 과제 시간 합계가 사용 가능 시간을 넘지 않아야 합니다.",
        ),
        _check(
            "course_name_preserved",
            plan.course_name.strip() == case.course_name,
            "error",
            "생성 계획의 과목명은 평가 사례의 사용자 입력과 같아야 합니다.",
        ),
        _check(
            "learning_cycle_present",
            {"learn", "review", "quiz"}.issubset(task_types),
            "warning",
            "가능한 경우 학습·복습·점검이 연결된 학습 주기를 구성해야 합니다.",
        ),
    ]
    combined_text = "\n".join(
        [
            plan.title,
            plan.course_name,
            plan.level_assessment,
            plan.weekly_goal,
            plan.strategy,
            plan.motivation_message,
            *(
                text
                for day in plan.days
                for text in (
                    day.daily_focus,
                    *(
                        task_text
                        for task in day.tasks
                        for task_text in (task.title, task.description)
                    ),
                )
            ),
        ]
    )
    checks.extend(_text_expectation_checks(case, combined_text))
    return _report(case, checks)


def _text_expectation_checks(
    case: AIQualityCase,
    text: str,
) -> list[AIQualityCheck]:
    """사례별 기대 용어와 금지 표현을 공통 방식으로 검사합니다."""

    return [
        _check(
            "expected_terms_present",
            all(
                _contains_normalized(text, term)
                for term in case.expected_terms
            ),
            "warning",
            "평가 사례의 핵심 개념이 생성 결과에 반영되어야 합니다.",
        ),
        _check(
            "expected_term_groups_present",
            all(
                any(
                    _contains_normalized(text, alternative)
                    for alternative in group
                )
                for group in case.expected_term_groups
            ),
            "warning",
            "핵심 개념의 승인된 표현 중 하나가 생성 결과에 반영되어야 합니다.",
        ),
        _check(
            "forbidden_terms_absent",
            not any(
                _contains_normalized(text, term)
                for term in case.forbidden_terms
            ),
            "error",
            "근거가 없거나 평가 목적에 어긋나는 금지 표현을 포함하지 않아야 합니다.",
        ),
    ]


def _sections_are_nonempty(text: str, sections: tuple[str, ...]) -> bool:
    """고정 Markdown 제목 사이에 비어 있지 않은 본문이 있는지 확인합니다."""

    positions = [text.find(section) for section in sections]
    if (
        any(position < 0 for position in positions)
        or positions != sorted(positions)
    ):
        return False
    for index, section in enumerate(sections):
        start = positions[index] + len(section)
        end = (
            positions[index + 1]
            if index + 1 < len(sections)
            else len(text)
        )
        if not text[start:end].strip():
            return False
    return True


def _normalize(value: str) -> str:
    """대소문자·유니코드·공백 차이를 제거한 비교 문자열을 만듭니다."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())


def _contains_normalized(text: str, term: str) -> bool:
    """표기와 공백 차이를 무시하고 용어 포함 여부를 확인합니다."""

    return _normalize(term) in _normalize(text)


def _check(
    key: str,
    passed: bool,
    severity: AIQualitySeverity,
    message: str,
) -> AIQualityCheck:
    """간결한 품질 검사 결과를 생성합니다."""

    return AIQualityCheck(
        key=key,
        passed=passed,
        severity=severity,
        message=message,
    )


def _report(
    case: AIQualityCase,
    checks: list[AIQualityCheck],
) -> AIQualityReport:
    """평가 사례 메타데이터와 검사 결과를 묶습니다."""

    return AIQualityReport(
        case_id=case.case_id,
        feature=case.feature,
        prompt_version=case.prompt_version,
        checks=checks,
    )


def _require_feature(
    case: AIQualityCase,
    expected_feature: AIQualityFeature,
) -> None:
    """잘못 연결한 평가 사례로 인한 거짓 통과를 방지합니다."""

    if case.feature != expected_feature:
        raise ValueError(
            f"{expected_feature} 결과에는 {case.feature} 평가 사례를 "
            "사용할 수 없습니다."
        )
