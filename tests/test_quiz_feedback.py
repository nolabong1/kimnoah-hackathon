import inspect
import unittest

from pydantic import ValidationError

from models.quiz import QuizQuestionDraft
from views.quiz_ui import (
    _get_choice_diagnostic,
    _render_quiz_result,
)


def _question_payload() -> dict:
    return {
        "question": "range(3)의 마지막 값은 무엇인가요?",
        "choices": ["2", "3", "0", "값이 없다"],
        "choice_feedback": [
            {
                "diagnosis_type": "correct_reasoning",
                "feedback": "종료값 직전의 값을 올바르게 찾았습니다.",
                "next_step": "시작값이 달라지는 경우도 확인해보세요.",
            },
            {
                "diagnosis_type": "boundary_error",
                "feedback": "종료값 3을 결과에 포함하는 것으로 해석했습니다.",
                "next_step": "range의 마지막 값과 종료값을 비교해보세요.",
            },
            {
                "diagnosis_type": "condition_omission",
                "feedback": "마지막 값이 아니라 기본 시작값을 선택했습니다.",
                "next_step": "질문이 요구하는 위치를 다시 확인해보세요.",
            },
            {
                "diagnosis_type": "concept_confusion",
                "feedback": "range가 정수 범위를 생성한다는 점을 다시 확인해야 합니다.",
                "next_step": "range(3)의 값을 순서대로 적어보세요.",
            },
        ],
        "correct_answer_index": 0,
        "explanation": "range(3)은 0, 1, 2를 생성하므로 마지막 값은 2입니다.",
        "concept_key": "python_range",
        "concept_name": "Python range 경계값",
        "evidence_key": "apply",
    }


class QuizFeedbackModelTests(unittest.TestCase):
    def test_choice_feedback_matches_all_four_choices(self):
        question = QuizQuestionDraft.model_validate(_question_payload())

        self.assertEqual(len(question.choice_feedback), 4)
        self.assertEqual(
            question.choice_feedback[1].diagnosis_type,
            "boundary_error",
        )

    def test_correct_choice_requires_correct_reasoning(self):
        payload = _question_payload()
        payload["choice_feedback"][0]["diagnosis_type"] = "boundary_error"

        with self.assertRaisesRegex(
            ValidationError,
            "correct_reasoning",
        ):
            QuizQuestionDraft.model_validate(payload)

    def test_wrong_choice_cannot_use_correct_reasoning(self):
        payload = _question_payload()
        payload["choice_feedback"][1]["diagnosis_type"] = "correct_reasoning"

        with self.assertRaisesRegex(
            ValidationError,
            "오답 원인",
        ):
            QuizQuestionDraft.model_validate(payload)


class QuizFeedbackViewTests(unittest.TestCase):
    def test_adaptive_analysis_uses_right_result_column(self):
        source = inspect.getsource(_render_quiz_result)

        self.assertIn(
            "result_column, diagnosis_column = st.columns",
            source,
        )
        self.assertIn("with result_column:", source)
        self.assertIn("with diagnosis_column:", source)
        self.assertLess(
            source.index("with result_column:"),
            source.index("with diagnosis_column:"),
        )
        self.assertIn("_render_adaptive_quiz_analysis(analysis)", source)

    def test_selected_wrong_choice_returns_korean_diagnostic(self):
        diagnostic = _get_choice_diagnostic(
            _question_payload(),
            selected_index=1,
        )

        self.assertEqual(diagnostic["label"], "경계값 오류")
        self.assertIn("종료값", diagnostic["feedback"])
        self.assertIn("비교", diagnostic["next_step"])

    def test_legacy_question_without_feedback_uses_existing_fallback(self):
        legacy_question = _question_payload()
        legacy_question.pop("choice_feedback")

        self.assertIsNone(
            _get_choice_diagnostic(
                legacy_question,
                selected_index=1,
            )
        )

    def test_malformed_saved_feedback_is_ignored_safely(self):
        malformed_question = _question_payload()
        malformed_question["choice_feedback"][1]["diagnosis_type"] = []

        self.assertIsNone(
            _get_choice_diagnostic(
                malformed_question,
                selected_index=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
