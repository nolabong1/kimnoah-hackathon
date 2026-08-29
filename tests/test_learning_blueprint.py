import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from models.quiz import QuizDraft
from models.learning_objective import LearningObjectiveContract
from models.review_material import ReviewMaterialDraft
from services.learning_blueprint_service import (
    build_learning_blueprint,
    get_target_depth,
    learning_blueprint_to_prompt_payload,
)
from services.quiz_service import generate_quiz
from services.review_material_service import generate_review_material


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
        title="range 경계값 학습",
        content_markdown="""
## 핵심 요약
range의 종료값 포함 여부를 이해합니다.
## 주요 개념
- 시작값과 종료값
## 상세 설명
종료값 자체는 결과에 포함되지 않습니다.
## 학습 예시
range(3)의 결과를 직접 추적합니다.
## 스스로 확인하기
range(2)의 결과를 예상하고 해설로 확인합니다.
""",
    )


def _valid_quiz() -> QuizDraft:
    return QuizDraft.model_validate(
        {
            "title": "range 경계값 점검",
            "questions": [
                {
                    "question": f"range({index + 2})의 결과로 알맞은 것은?",
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
                            "next_step": "시작값이 있는 range에도 같은 원리를 적용해보세요.",
                        },
                        {
                            "diagnosis_type": "boundary_error",
                            "feedback": "종료 경계를 결과에 포함하는 것으로 해석했습니다.",
                            "next_step": "생성되는 마지막 값과 종료값을 비교해보세요.",
                        },
                        {
                            "diagnosis_type": "concept_confusion",
                            "feedback": "range가 값을 생성하는 기본 동작을 다시 확인해야 합니다.",
                            "next_step": "range(2)를 직접 나열해보세요.",
                        },
                        {
                            "diagnosis_type": "overgeneralization",
                            "feedback": "모든 range가 한 값만 만든다고 지나치게 일반화했습니다.",
                            "next_step": "종료값이 달라질 때 결과 개수를 비교해보세요.",
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


class LearningBlueprintTests(unittest.TestCase):
    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_review_request_includes_selected_learning_objective(
        self,
        get_review_client,
        get_review_model,
    ):
        fake_client = FakeOpenAIClient(_valid_review_material())
        get_review_client.return_value = fake_client
        get_review_model.return_value = "test-model"
        objective = LearningObjectiveContract.model_validate(
            {
                "objective_key": "python_range",
                "title": "range 경계값 적용",
                "description": "종료값 제외 규칙을 설명하고 적용한다.",
                "target_depth": "foundation",
                "evidence_requirements": [
                    {"key": "explain", "description": "규칙을 설명한다."},
                    {"key": "apply", "description": "결과를 예측한다."},
                    {
                        "key": "differentiate",
                        "description": "포함과 제외를 구분한다.",
                    },
                ],
            }
        )

        generate_review_material(
            course_name="Python",
            goal="range를 이해한다.",
            current_level=3,
            task_title="range 경계값 익히기",
            task_description="range 결과를 예측한다.",
            task_type="review",
            estimated_minutes=20,
            learning_objective=objective,
        )

        request = fake_client.responses.calls[0]
        payload = json.loads(request["input"][1]["content"])
        self.assertEqual(
            payload["learning_objective"]["objective_key"],
            "python_range",
        )
        self.assertIn(
            "learning_objective는 같은 계획의 과제",
            request["input"][0]["content"],
        )

    def test_level_scale_maps_to_stable_depth_bands(self):
        self.assertEqual(get_target_depth(1), "foundation")
        self.assertEqual(get_target_depth(3), "foundation")
        self.assertEqual(get_target_depth(4), "developing")
        self.assertEqual(get_target_depth(7), "developing")
        self.assertEqual(get_target_depth(8), "advanced")
        self.assertEqual(get_target_depth(10), "advanced")

    def test_blueprint_is_deterministic_and_has_ordered_evidence(self):
        first = build_learning_blueprint(
            course_name=" Python ",
            goal=" range 경계값을 설명한다. ",
            current_level=3,
            task_title=" range 익히기 ",
            task_description=" ",
            estimated_minutes=20,
        )
        second = build_learning_blueprint(
            course_name="Python",
            goal="range 경계값을 설명한다.",
            current_level=3,
            task_title="range 익히기",
            task_description="",
            estimated_minutes=20,
        )

        self.assertEqual(first, second)
        self.assertEqual(first.task_scope, "range 익히기")
        self.assertEqual(
            [item.key for item in first.evidence_requirements],
            ["explain", "apply", "differentiate"],
        )

    def test_prompt_payload_contains_no_runtime_or_user_identifiers(self):
        blueprint = build_learning_blueprint(
            course_name="Python",
            goal="range의 동작을 이해한다.",
            current_level=5,
            task_title="range 적용",
            task_description="예제에 range를 적용한다.",
            estimated_minutes=25,
        )

        payload = learning_blueprint_to_prompt_payload(blueprint)
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("user_id", serialized)
        self.assertNotIn("task_id", serialized)
        self.assertNotIn("plan_id", serialized)

    def test_invalid_blueprint_input_is_rejected_before_ai_call(self):
        with self.assertRaisesRegex(ValueError, "현재 수준"):
            build_learning_blueprint(
                course_name="Python",
                goal="range 이해",
                current_level=11,
                task_title="range 학습",
                task_description="range를 설명한다.",
                estimated_minutes=20,
            )

    def test_quiz_rejects_unaligned_evidence_distribution(self):
        quiz_data = _valid_quiz().model_dump()
        for question in quiz_data["questions"]:
            question["evidence_key"] = "explain"

        with self.assertRaisesRegex(
            ValueError,
            "설명 2문항, 적용 2문항, 오해 구분 1문항",
        ):
            QuizDraft.model_validate(quiz_data)

    @patch("services.quiz_service.get_openai_model")
    @patch("services.quiz_service.get_openai_client")
    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_review_and_quiz_requests_share_the_same_blueprint_contract(
        self,
        get_review_client,
        get_review_model,
        get_quiz_client,
        get_quiz_model,
    ):
        review_client = FakeOpenAIClient(_valid_review_material())
        quiz_client = FakeOpenAIClient(_valid_quiz())
        get_review_client.return_value = review_client
        get_review_model.return_value = "test-model"
        get_quiz_client.return_value = quiz_client
        get_quiz_model.return_value = "test-model"
        shared_inputs = {
            "course_name": "Python",
            "goal": "range의 종료값 포함 여부를 설명하고 적용한다.",
            "current_level": 3,
            "task_title": "range 경계값 익히기",
            "task_description": "range 결과를 예측하고 이유를 설명한다.",
            "estimated_minutes": 20,
        }

        generate_review_material(
            **shared_inputs,
            task_type="review",
        )
        generate_quiz(
            **shared_inputs,
            task_type="quiz",
        )

        review_request = review_client.responses.calls[0]
        quiz_request = quiz_client.responses.calls[0]
        review_payload = json.loads(review_request["input"][1]["content"])
        quiz_payload = json.loads(quiz_request["input"][1]["content"])

        self.assertEqual(
            review_payload["learning_blueprint"],
            quiz_payload["learning_blueprint"],
        )
        self.assertIn(
            "학습자료와 평가가 공유하는 학습 계약",
            review_request["input"][0]["content"],
        )
        self.assertIn(
            "학습자료와 평가가 공유하는 학습 계약",
            quiz_request["input"][0]["content"],
        )


if __name__ == "__main__":
    unittest.main()
