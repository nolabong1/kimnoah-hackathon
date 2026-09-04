import unittest

from models.quiz import QuizDraft
from models.review_material import ReviewMaterialDraft
from models.study_plan import WeeklyStudyPlan
from models.tutor import TutorGuidance
from services.ai_quality_service import (
    evaluate_quiz_quality,
    evaluate_review_material_quality,
    evaluate_study_plan_quality,
    evaluate_tutor_quality,
    load_ai_quality_cases,
)
from services.quiz_service import QUIZ_PROMPT_VERSION
from services.review_material_service import (
    REVIEW_MATERIAL_PROMPT_VERSION,
)
from services.study_plan_service import STUDY_PLAN_PROMPT_VERSION
from services.tutor_service import TUTOR_GUIDANCE_PROMPT_VERSION


def _case(case_id: str):
    return next(
        case
        for case in load_ai_quality_cases()
        if case.case_id == case_id
    )


def _plan_learning_objectives() -> list[dict]:
    return [
        {
            "objective_key": "loop_fundamentals",
            "title": "반복문 기본 원리",
            "description": "반복문의 실행 흐름과 종료 조건을 설명합니다.",
            "target_depth": "foundation",
            "evidence_requirements": [
                {"key": "explain", "description": "실행 흐름을 설명합니다."},
                {"key": "apply", "description": "반복문을 작성합니다."},
                {"key": "differentiate", "description": "조건 차이를 구분합니다."},
            ],
        },
        {
            "objective_key": "loop_application",
            "title": "반복문 문제 적용",
            "description": "문제 조건을 반복 구조로 변환해 적용합니다.",
            "target_depth": "foundation",
            "evidence_requirements": [
                {"key": "explain", "description": "구조 선택을 설명합니다."},
                {"key": "apply", "description": "문제를 해결합니다."},
                {"key": "differentiate", "description": "오류를 구분합니다."},
            ],
        },
    ]


class AIQualityHarnessTests(unittest.TestCase):
    def test_representative_cases_are_unique_and_cover_core_features(self):
        cases = load_ai_quality_cases()

        self.assertEqual(len(cases), 12)
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertEqual(
            {case.feature for case in cases},
            {"study_plan", "review_material", "quiz", "tutor"},
        )
        for feature in {case.feature for case in cases}:
            self.assertGreaterEqual(
                sum(case.feature == feature for case in cases),
                3,
            )
        self.assertTrue(any(case.learner_level <= 3 for case in cases))
        self.assertTrue(
            any(4 <= case.learner_level <= 7 for case in cases)
        )
        self.assertTrue(any(case.learner_level >= 8 for case in cases))
        self.assertGreaterEqual(
            len({case.course_name for case in cases}),
            8,
        )
        review_versions = {
            case.prompt_version
            for case in cases
            if case.feature == "review_material"
        }
        quiz_versions = {
            case.prompt_version
            for case in cases
            if case.feature == "quiz"
        }
        study_plan_versions = {
            case.prompt_version
            for case in cases
            if case.feature == "study_plan"
        }
        tutor_versions = {
            case.prompt_version
            for case in cases
            if case.feature == "tutor"
        }
        self.assertEqual(
            review_versions,
            {REVIEW_MATERIAL_PROMPT_VERSION},
        )
        self.assertEqual(quiz_versions, {QUIZ_PROMPT_VERSION})
        self.assertEqual(
            study_plan_versions,
            {STUDY_PLAN_PROMPT_VERSION},
        )
        self.assertEqual(tutor_versions, {TUTOR_GUIDANCE_PROMPT_VERSION})

    def test_representative_cases_cover_approved_quality_dimensions(self):
        cases = load_ai_quality_cases()

        dimensions = {
            dimension
            for case in cases
            for dimension in case.quality_dimensions
        }

        self.assertEqual(
            dimensions,
            {
                "schedule_feasibility",
                "scope_alignment",
                "source_grounding",
                "concept_coverage",
                "misconception_diagnosis",
                "answer_leakage",
                "difficulty_alignment",
                "prompt_injection_resistance",
            },
        )

    def test_review_material_detects_unsupported_claim(self):
        case = _case("review_python_range_boundary")
        material = ReviewMaterialDraft(
            title="range 경계값 복습",
            content_markdown="""
## 핵심 요약
range는 종료값 직전까지 숫자를 만듭니다.
## 주요 개념
- range
- 종료값
## 상세 설명
제공된 교재에 따르면 종료값은 포함되지 않습니다.
## 학습 예시
range(3)은 0, 1, 2를 만듭니다.
## 스스로 확인하기
range(2)의 결과를 설명하고 정답과 해설을 확인하세요.
""",
        )

        report = evaluate_review_material_quality(case, material)

        self.assertFalse(report.is_acceptable)
        self.assertIn(
            "forbidden_terms_absent",
            [check.key for check in report.failed_checks],
        )

    def test_review_material_accepts_approved_alternative_term(self):
        case = _case("review_python_range_boundary")
        material = ReviewMaterialDraft(
            title="range 끝값 복습",
            content_markdown="""
## 핵심 요약
range는 끝값 직전까지 숫자를 만듭니다.
## 주요 개념
- range의 끝값
## 상세 설명
끝값 자체는 결과에 포함되지 않습니다.
## 학습 예시
range(3)은 0, 1, 2를 만듭니다.
## 스스로 확인하기
range(2)의 결과를 예상하고 정답과 해설을 확인하세요.
""",
        )

        report = evaluate_review_material_quality(case, material)

        self.assertTrue(report.is_acceptable)
        self.assertNotIn(
            "expected_term_groups_present",
            [check.key for check in report.failed_checks],
        )

    def test_quiz_checks_expected_concept_and_disallowed_choice(self):
        case = _case("quiz_python_range_boundary")
        quiz = QuizDraft.model_validate(
            {
                "title": "Python range 점검",
                "questions": [
                    {
                        "question": (
                            f"range({index + 2})의 종료값 설명으로 알맞은 것은?"
                        ),
                        "choices": [
                            "종료값 직전까지 반복한다",
                            "종료값을 포함한다",
                            "모두 정답",
                            "항상 한 번만 반복한다",
                        ],
                        "choice_feedback": [
                            {
                                "diagnosis_type": "correct_reasoning",
                                "feedback": "종료값이 제외되는 규칙을 올바르게 적용했습니다.",
                                "next_step": "시작값이 있는 경우도 확인해보세요.",
                            },
                            {
                                "diagnosis_type": "boundary_error",
                                "feedback": "종료 경계를 포함하는 것으로 해석했습니다.",
                                "next_step": "마지막 생성값을 확인해보세요.",
                            },
                            {
                                "diagnosis_type": "concept_confusion",
                                "feedback": "선택지별 참·거짓을 구분하지 못했습니다.",
                                "next_step": "각 선택지를 따로 검토해보세요.",
                            },
                            {
                                "diagnosis_type": "overgeneralization",
                                "feedback": "반복 횟수를 한 가지 경우로 일반화했습니다.",
                                "next_step": "서로 다른 종료값을 비교해보세요.",
                            },
                        ],
                        "correct_answer_index": 0,
                        "explanation": (
                            "range는 지정한 종료값 자체를 포함하지 않습니다."
                        ),
                        "concept_key": "python_range",
                        "concept_name": "Python range 경계값",
                        "evidence_key": (
                            "explain"
                            if index < 2
                            else "apply"
                            if index < 4
                            else "differentiate"
                        ),
                    }
                    for index in range(5)
                ],
            }
        )

        report = evaluate_quiz_quality(case, quiz)

        self.assertFalse(report.is_acceptable)
        self.assertIn(
            "disallowed_choices_absent",
            [check.key for check in report.failed_checks],
        )

    def test_tutor_detects_final_answer_leak_in_hint(self):
        case = _case("tutor_linear_equation_hint")
        guidance = TutorGuidance.model_validate(
            {
                "problem_summary": "등식의 성질로 x를 구합니다.",
                "required_concepts": ["등식의 성질", "일차방정식"],
                "hints": [
                    {
                        "level": 1,
                        "title": "항 확인",
                        "content": "미지수 항과 상수항을 구분하세요.",
                        "guiding_question": "어느 항을 먼저 옮길까요?",
                    },
                    {
                        "level": 2,
                        "title": "양변 정리",
                        "content": "등식의 양변에 같은 연산을 적용하세요.",
                        "guiding_question": "양변에서 무엇을 뺄까요?",
                    },
                    {
                        "level": 3,
                        "title": "계수 확인",
                        "content": "양변을 정리하면 최종 답은 x = 3입니다.",
                        "guiding_question": "원래 식에 대입하면 어떤가요?",
                    },
                ],
                "final_solution": {
                    "final_answer": "x = 3",
                    "reasoning_steps": [
                        "양변에서 2를 뺍니다.",
                        "2로 나눕니다.",
                    ],
                    "why_solution_works": (
                        "등식의 양변에 같은 연산을 적용했습니다."
                    ),
                    "common_mistakes": [
                        "이항할 때 부호를 잘못 바꾸는 실수"
                    ],
                    "self_check_question": "대입했을 때 양변이 같나요?",
                },
            }
        )

        report = evaluate_tutor_quality(case, guidance)

        self.assertFalse(report.is_acceptable)
        self.assertIn(
            "final_answer_hidden_in_hints",
            [check.key for check in report.failed_checks],
        )

    def test_study_plan_checks_time_limit_and_learning_cycle(self):
        case = _case("study_plan_python_loops_beginner")
        plan = WeeklyStudyPlan.model_validate(
            {
                "title": "Python 반복문 7일 계획",
                "course_name": "Python",
                "level_assessment": "반복문을 처음 적용하는 단계입니다.",
                "weekly_goal": "반복문으로 간단한 문제를 해결합니다.",
                "strategy": "개념 학습 뒤 복습과 퀴즈를 진행합니다.",
                "learning_objectives": _plan_learning_objectives(),
                "motivation_message": "매일 정한 범위까지 진행해보세요.",
                "days": [
                    {
                        "day_offset": day_offset,
                        "daily_focus": "반복문 적용",
                        "tasks": [
                            {
                                "objective_key": (
                                    "loop_fundamentals"
                                    if day_offset < 4
                                    else "loop_application"
                                ),
                                "title": "반복문 연습",
                                "description": (
                                    "예제를 풀고 결과를 설명합니다."
                                ),
                                "task_type": (
                                    "review"
                                    if day_offset == 4
                                    else "quiz"
                                    if day_offset == 6
                                    else "learn"
                                ),
                                "estimated_minutes": 30,
                            }
                        ],
                    }
                    for day_offset in range(7)
                ],
            }
        )
        schedule = {f"{day_offset}일차": 20 for day_offset in range(7)}

        report = evaluate_study_plan_quality(case, plan, schedule)

        self.assertFalse(report.is_acceptable)
        self.assertIn(
            "daily_time_limits_respected",
            [check.key for check in report.failed_checks],
        )

    def test_quality_warning_does_not_block_an_otherwise_safe_plan(self):
        case = _case("study_plan_python_loops_beginner")
        plan = WeeklyStudyPlan.model_validate(
            {
                "title": "Python 반복문 기초 계획",
                "course_name": "Python",
                "level_assessment": "반복문을 처음 배우는 단계입니다.",
                "weekly_goal": "반복문의 실행 순서를 설명합니다.",
                "strategy": "짧은 예제를 매일 직접 실행합니다.",
                "learning_objectives": _plan_learning_objectives(),
                "motivation_message": "정해진 범위에 집중해보세요.",
                "days": [
                    {
                        "day_offset": day_offset,
                        "daily_focus": "반복문 기초",
                        "tasks": [
                            {
                                "objective_key": (
                                    "loop_fundamentals"
                                    if day_offset < 4
                                    else "loop_application"
                                ),
                                "title": "반복문 예제 실행",
                                "description": "예제를 실행하고 결과를 설명합니다.",
                                "task_type": "learn",
                                "estimated_minutes": 20,
                            }
                        ],
                    }
                    for day_offset in range(7)
                ],
            }
        )
        schedule = {f"{day_offset}일차": 20 for day_offset in range(7)}

        report = evaluate_study_plan_quality(case, plan, schedule)

        self.assertTrue(report.is_acceptable)
        self.assertEqual(
            [check.key for check in report.failed_checks],
            ["learning_cycle_present"],
        )


if __name__ == "__main__":
    unittest.main()
