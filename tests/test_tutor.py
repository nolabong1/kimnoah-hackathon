import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from models.tutor import (
    TutorAttemptFeedback,
    TutorFinalSolution,
    TutorGuidance,
    TutorHint,
)
from services.tutor_service import (
    MAX_TUTOR_ATTEMPT_CHARS,
    MAX_TUTOR_QUESTION_CHARS,
    REFERENCE_LIMIT_MARKER,
    TutorInputValidationError,
    generate_tutor_attempt_feedback,
    generate_tutor_guidance,
    limit_reference_context,
    validate_tutor_attempt,
    validate_tutor_question,
)
from views.tutor_state import (
    ACTIVE_SESSION_ID_KEY,
    FINAL_ANSWER_CONFIRMED_KEY,
    VISIBLE_HINT_LEVEL_KEY,
    advance_hint_level,
    clear_tutor_state,
    create_tutor_session_state,
    get_visible_hints,
    is_final_solution_visible,
    previous_hint_level,
)


def build_guidance() -> TutorGuidance:
    return TutorGuidance(
        problem_summary="미지수 x를 구하는 일차방정식입니다.",
        required_concepts=["등식의 성질", "일차방정식"],
        hints=[
            TutorHint(
                level=1,
                title="항의 위치 살펴보기",
                content="미지수 항과 상수항이 어느 쪽에 있는지 확인하세요.",
                guiding_question="어떤 항을 먼저 옮기면 좋을까요?",
            ),
            TutorHint(
                level=2,
                title="등식의 성질 사용하기",
                content="양변에 같은 연산을 적용해 미지수 항을 남기세요.",
                guiding_question="양변에서 먼저 뺄 값은 무엇인가요?",
            ),
            TutorHint(
                level=3,
                title="마지막 계산 준비",
                content="미지수의 계수로 양변을 나누기 직전까지 정리하세요.",
                guiding_question="마지막에 어떤 수로 나누어야 하나요?",
            ),
        ],
        final_solution=TutorFinalSolution(
            final_answer="x = 3",
            reasoning_steps=[
                "양변에서 2를 뺍니다.",
                "남은 양변을 2로 나눕니다.",
            ],
            why_solution_works=(
                "등식의 양변에 같은 연산을 적용하면 등호 관계가 유지됩니다."
            ),
            common_mistakes=["항을 이항할 때 부호를 바꾸지 않는 실수"],
            self_check_question="구한 값을 원래 식에 대입하면 양변이 같나요?",
        ),
    )


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


class TutorModelTests(unittest.TestCase):
    def test_guidance_requires_three_ordered_hints(self):
        guidance = build_guidance()
        self.assertEqual([hint.level for hint in guidance.hints], [1, 2, 3])

        invalid_data = guidance.model_dump()
        invalid_data["hints"][0]["level"] = 2
        with self.assertRaises(ValidationError):
            TutorGuidance.model_validate(invalid_data)

    def test_attempt_feedback_parses_without_revealing_answer(self):
        feedback = TutorAttemptFeedback(
            assessment="partially_correct",
            what_was_done_well="미지수 항을 한쪽에 모았습니다.",
            issue="상수항을 옮길 때 부호를 다시 확인해야 합니다.",
            next_step="이항한 뒤 양변을 다시 정리해보세요.",
            recommended_hint_level=2,
            reveals_final_answer=False,
        )
        self.assertEqual(feedback.assessment, "partially_correct")

        with self.assertRaises(ValidationError):
            TutorAttemptFeedback(
                assessment="correct",
                what_was_done_well="접근이 적절합니다.",
                issue="중요한 오류는 없습니다.",
                next_step="스스로 검산해보세요.",
                recommended_hint_level=1,
                reveals_final_answer=True,
            )


class TutorStateTests(unittest.TestCase):
    def setUp(self):
        self.guidance = build_guidance()
        self.state = create_tutor_session_state(
            session_id="session-1",
            user_id="user-1",
            plan_id="plan-1",
            task_id=None,
            material_key=None,
            course_name="수학",
            task_title=None,
            reference_title=None,
            reference_context=None,
            reference_was_limited=False,
            question="2x + 2 = 8에서 x를 구하세요.",
            original_attempt="2를 먼저 빼려고 합니다.",
            guidance=self.guidance,
        )

    def test_initial_state_reveals_only_hint_one(self):
        self.assertEqual(self.state[VISIBLE_HINT_LEVEL_KEY], 1)
        visible = get_visible_hints(
            self.guidance,
            self.state[VISIBLE_HINT_LEVEL_KEY],
        )
        self.assertEqual([hint.level for hint in visible], [1])

    @patch("services.tutor_service.get_openai_client")
    def test_hint_navigation_does_not_call_openai(self, mock_client):
        level = advance_hint_level(1)
        self.assertEqual(level, 2)
        level = advance_hint_level(level)
        self.assertEqual(level, 3)
        self.assertEqual(previous_hint_level(level), 2)
        mock_client.assert_not_called()

    def test_final_solution_hidden_until_confirmation(self):
        self.assertFalse(is_final_solution_visible(self.state))
        self.state[FINAL_ANSWER_CONFIRMED_KEY] = True
        self.assertTrue(is_final_solution_visible(self.state))

    def test_reset_removes_only_tutor_keys(self):
        state = {
            **self.state,
            "saved_plan_id": "keep-me",
            "task_completion_feedback": {"exp": 10},
        }
        clear_tutor_state(state)
        self.assertNotIn(ACTIVE_SESSION_ID_KEY, state)
        self.assertEqual(state["saved_plan_id"], "keep-me")
        self.assertIn("task_completion_feedback", state)


class TutorServiceTests(unittest.TestCase):
    def test_empty_and_oversized_inputs_are_rejected(self):
        with self.assertRaises(TutorInputValidationError):
            validate_tutor_question("   ")
        with self.assertRaises(TutorInputValidationError):
            validate_tutor_question("가" * (MAX_TUTOR_QUESTION_CHARS + 1))
        with self.assertRaises(TutorInputValidationError):
            validate_tutor_attempt(
                "나" * (MAX_TUTOR_ATTEMPT_CHARS + 1),
                required=True,
            )

    def test_reference_limit_is_deterministic(self):
        source = "가" * 100
        first, first_limited = limit_reference_context(source, max_chars=50)
        second, second_limited = limit_reference_context(source, max_chars=50)
        self.assertEqual(first, second)
        self.assertTrue(first_limited)
        self.assertTrue(second_limited)
        self.assertEqual(len(first), 50)
        self.assertTrue(first.endswith(REFERENCE_LIMIT_MARKER))

    @patch("services.tutor_service.get_openai_model", return_value="test-model")
    @patch("services.tutor_service.get_openai_client")
    def test_start_calls_openai_once(self, mock_client, _mock_model):
        fake_client = FakeOpenAIClient(build_guidance())
        mock_client.return_value = fake_client

        result = generate_tutor_guidance(
            course_name="수학",
            goal="일차방정식 이해",
            current_level=3,
            task_title=None,
            task_description=None,
            reference_title=None,
            reference_context=None,
            question="2x + 2 = 8에서 x를 구하세요.",
            user_attempt="양변에서 2를 빼려고 합니다.",
        )

        self.assertEqual(result.guidance.hints[0].level, 1)
        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertIs(
            fake_client.responses.calls[0]["text_format"],
            TutorGuidance,
        )

    @patch("services.tutor_service.get_openai_model", return_value="test-model")
    @patch("services.tutor_service.get_openai_client")
    def test_feedback_calls_openai_once_and_parses(
        self,
        mock_client,
        _mock_model,
    ):
        parsed_feedback = TutorAttemptFeedback(
            assessment="needs_revision",
            what_was_done_well="식의 구조를 확인했습니다.",
            issue="이항 과정의 부호를 확인해야 합니다.",
            next_step="양변에서 같은 값을 빼보세요.",
            recommended_hint_level=2,
            reveals_final_answer=False,
        )
        fake_client = FakeOpenAIClient(parsed_feedback)
        mock_client.return_value = fake_client

        feedback = generate_tutor_attempt_feedback(
            course_name="수학",
            task_title=None,
            reference_title=None,
            reference_context=None,
            question="2x + 2 = 8에서 x를 구하세요.",
            original_attempt="2를 옮깁니다.",
            revised_attempt="양변에서 2를 뺍니다.",
            guidance=build_guidance(),
            revealed_hint_level=1,
        )

        self.assertEqual(feedback.assessment, "needs_revision")
        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertIs(
            fake_client.responses.calls[0]["text_format"],
            TutorAttemptFeedback,
        )


if __name__ == "__main__":
    unittest.main()
