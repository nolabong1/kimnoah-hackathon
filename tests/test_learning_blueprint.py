import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from models.quiz import QuizDraft
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
