import json
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from models.quiz import QuizDraft
from models.review_material import ReviewMaterialDraft
from services.learner_context_service import (
    MAX_FOCUS_CONCEPTS,
    MAX_STABLE_CONCEPTS,
    build_learner_context,
    learner_context_to_prompt_payload,
    load_learner_context,
    summarize_repeated_diagnoses,
)
from services.concept_service import normalize_course_key
from services.quiz_service import generate_quiz
from services.review_material_service import generate_review_material


def _mastery(
    index: int,
    *,
    score: int,
    is_weak: bool,
    last_answer_correct: bool | None,
    consecutive_incorrect: int = 0,
    recent_diagnosis_types: list[str] | None = None,
) -> dict:
    return {
        "concept_id": f"private-id-{index}",
        "concept_key": f"concept_{index}",
        "concept_name": f"개념 {index}",
        "mastery_score": score,
        "correct_count": index + 1,
        "incorrect_count": consecutive_incorrect + 1,
        "consecutive_incorrect_count": consecutive_incorrect,
        "last_answer_correct": last_answer_correct,
        "last_assessed_at": "2026-08-19T00:00:00+00:00",
        "is_weak": is_weak,
        "recent_diagnosis_types": recent_diagnosis_types or [],
    }


class FakeResponses:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed_output)


class FakeOpenAIClient:
    def __init__(self, parsed_output):
        self.responses = FakeResponses(parsed_output)


def _valid_review_material() -> ReviewMaterialDraft:
    return ReviewMaterialDraft(
        title="반복문 맞춤 복습",
        content_markdown="""
## 핵심 요약
반복문의 실행 흐름을 확인합니다.
## 주요 개념
- range 종료값
## 상세 설명
종료값 직전까지 반복합니다.
## 학습 예시
range(3)의 결과를 추적합니다.
## 스스로 확인하기
결과를 예상한 뒤 정답과 해설을 확인합니다.
""",
    )


def _valid_quiz() -> QuizDraft:
    return QuizDraft.model_validate(
        {
            "title": "반복문 맞춤 점검",
            "questions": [
                {
                    "question": f"range({index + 2})의 결과를 고르세요.",
                    "choices": [
                        "종료값 직전까지 생성",
                        "종료값까지 생성",
                        "항상 빈 결과",
                        "항상 한 값만 생성",
                    ],
                    "choice_feedback": [
                        {
                            "diagnosis_type": "correct_reasoning",
                            "feedback": "종료값이 제외되는 규칙을 올바르게 적용했습니다.",
                            "next_step": "다른 종료값에도 같은 원리를 적용해보세요.",
                        },
                        {
                            "diagnosis_type": "boundary_error",
                            "feedback": "종료 경계를 결과에 포함하는 것으로 해석했습니다.",
                            "next_step": "마지막 결과와 종료값을 비교해보세요.",
                        },
                        {
                            "diagnosis_type": "concept_confusion",
                            "feedback": "range의 기본 생성 규칙을 다시 확인해야 합니다.",
                            "next_step": "range(2)를 직접 나열해보세요.",
                        },
                        {
                            "diagnosis_type": "overgeneralization",
                            "feedback": "range 결과 개수를 한 가지 경우로 일반화했습니다.",
                            "next_step": "종료값에 따른 결과 개수를 비교해보세요.",
                        },
                    ],
                    "correct_answer_index": 0,
                    "explanation": "range는 종료값 자체를 포함하지 않습니다.",
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


class LearnerContextTests(unittest.TestCase):
    def test_empty_masteries_do_not_create_artificial_context(self):
        self.assertIsNone(build_learner_context("python", []))
        self.assertIsNone(learner_context_to_prompt_payload(None))

    def test_only_repeated_recent_diagnoses_are_summarized(self):
        result = summarize_repeated_diagnoses(
            [
                "boundary_error",
                "condition_omission",
                "boundary_error",
                "condition_omission",
                "concept_confusion",
                "concept_confusion",
            ]
        )

        self.assertEqual(
            [signal.diagnosis_type for signal in result],
            ["condition_omission", "boundary_error"],
        )
        self.assertEqual(
            [signal.occurrence_count for signal in result],
            [2, 2],
        )

    def test_single_or_unknown_diagnosis_is_not_personalized(self):
        result = summarize_repeated_diagnoses(
            ["boundary_error", "unknown", None]
        )

        self.assertEqual(result, [])

    def test_context_prioritizes_and_limits_concepts_deterministically(self):
        masteries = [
            _mastery(
                index,
                score=40 + index,
                is_weak=True,
                last_answer_correct=False,
                consecutive_incorrect=8 - index,
            )
            for index in range(8)
        ]
        masteries.extend(
            _mastery(
                index,
                score=95 - index,
                is_weak=False,
                last_answer_correct=True,
            )
            for index in range(8, 12)
        )

        context = build_learner_context("python", masteries)

        self.assertIsNotNone(context)
        self.assertEqual(len(context.focus_concepts), MAX_FOCUS_CONCEPTS)
        self.assertEqual(len(context.stable_concepts), MAX_STABLE_CONCEPTS)
        self.assertEqual(context.focus_concepts[0].concept_key, "concept_0")
        payload = learner_context_to_prompt_payload(context)
        self.assertNotIn("concept_id", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(
            "last_assessed_at",
            json.dumps(payload, ensure_ascii=False),
        )

    @patch(
        "services.learner_context_service.get_course_concept_masteries"
    )
    def test_loader_filters_by_normalized_user_and_course(
        self,
        get_masteries,
    ):
        get_masteries.return_value = [
            _mastery(
                1,
                score=45,
                is_weak=True,
                last_answer_correct=False,
                consecutive_incorrect=2,
            )
        ]

        context = load_learner_context(
            supabase=object(),
            user_id="user-1",
            course_name=" Python ",
        )

        expected_course_key = normalize_course_key(" Python ")
        self.assertEqual(context.course_key, expected_course_key)
        get_masteries.assert_called_once_with(
            supabase=ANY,
            user_id="user-1",
            course_key=expected_course_key,
        )

    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_review_material_request_contains_limited_learner_context(
        self,
        get_client,
        get_model,
    ):
        context = build_learner_context(
            "python",
            [
                _mastery(
                    1,
                    score=45,
                    is_weak=True,
                    last_answer_correct=False,
                    consecutive_incorrect=2,
                    recent_diagnosis_types=[
                        "boundary_error",
                        "boundary_error",
                    ],
                )
            ],
        )
        fake_client = FakeOpenAIClient(_valid_review_material())
        get_client.return_value = fake_client
        get_model.return_value = "test-model"

        result = generate_review_material(
            course_name="Python",
            goal="반복문 이해",
            current_level=3,
            task_title="range 복습",
            task_description="range 종료값을 설명합니다.",
            task_type="review",
            estimated_minutes=20,
            learner_context=context,
        )

        self.assertEqual(result.title, "반복문 맞춤 복습")
        request = fake_client.responses.calls[0]
        payload = json.loads(request["input"][1]["content"])
        self.assertEqual(
            payload["learner_context"]["focus_concepts"][0]["concept_key"],
            "concept_1",
        )
        self.assertEqual(
            payload["learner_context"]["focus_concepts"][0][
                "repeated_diagnoses"
            ],
            [
                {
                    "diagnosis_type": "boundary_error",
                    "occurrence_count": 2,
                }
            ],
        )
        self.assertIn("learner_context가 제공되면", request["input"][0]["content"])

    @patch("services.quiz_service.get_openai_model")
    @patch("services.quiz_service.get_openai_client")
    def test_quiz_request_contains_limited_learner_context(
        self,
        get_client,
        get_model,
    ):
        context = build_learner_context(
            "python",
            [
                _mastery(
                    1,
                    score=45,
                    is_weak=True,
                    last_answer_correct=False,
                    consecutive_incorrect=2,
                    recent_diagnosis_types=[
                        "boundary_error",
                        "boundary_error",
                    ],
                )
            ],
        )
        fake_client = FakeOpenAIClient(_valid_quiz())
        get_client.return_value = fake_client
        get_model.return_value = "test-model"

        result = generate_quiz(
            course_name="Python",
            goal="반복문 이해",
            current_level=3,
            task_title="range 퀴즈",
            task_description="range 종료값을 점검합니다.",
            task_type="quiz",
            estimated_minutes=20,
            existing_concepts=[
                {
                    "concept_key": "python_range",
                    "concept_name": "Python range 경계값",
                }
            ],
            learner_context=context,
        )

        self.assertEqual(result.title, "반복문 맞춤 점검")
        request = fake_client.responses.calls[0]
        payload = json.loads(request["input"][1]["content"])
        self.assertEqual(
            payload["learner_context"]["focus_concepts"][0]["recent_result"],
            "incorrect",
        )
        self.assertEqual(
            payload["learner_context"]["focus_concepts"][0][
                "repeated_diagnoses"
            ][0]["diagnosis_type"],
            "boundary_error",
        )
        self.assertIn("learner_context가 제공되면", request["input"][0]["content"])


if __name__ == "__main__":
    unittest.main()
