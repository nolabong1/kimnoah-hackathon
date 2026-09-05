import unittest
from datetime import date

from views.create_plan_view import (
    COURSE_NAME_INPUT_KEY,
    CURRENT_LEVEL_INPUT_KEY,
    START_DATE_INPUT_KEY,
    STUDY_GOAL_INPUT_KEY,
    clear_create_plan_input_state,
    get_available_minutes_input_key,
)
from views.source_review_material_view import (
    RESULT_STATE_KEY,
    SOURCE_TYPE_KEY,
    TEXT_KEY,
    TITLE_KEY,
    VIEW_MODE_KEY,
)
from views.test_sample_input_state import (
    SAMPLE_PLAN,
    SAMPLE_SOURCE_REVIEW,
    SAMPLE_TUTOR,
    SAMPLE_WEEKLY_REFLECTION,
    apply_sample_input,
)
from views.tutor_view import SETUP_ATTEMPT_KEY, SETUP_QUESTION_KEY
from views.weekly_review_state import SAMPLE_REFLECTION_PENDING_KEY


TODAY = date(2026, 9, 5)


class SampleInputStateTests(unittest.TestCase):
    def test_plan_sample_fills_inputs_and_clears_only_old_draft(self):
        state = {
            "generated_plan": {"title": "이전 계획"},
            "unrelated": "keep",
        }

        target, message = apply_sample_input(state, SAMPLE_PLAN, TODAY)

        self.assertEqual(target, "계획 만들기")
        self.assertIn("샘플 입력", message)
        self.assertEqual(state[COURSE_NAME_INPUT_KEY], "파이썬 기초")
        self.assertTrue(state[STUDY_GOAL_INPUT_KEY])
        self.assertEqual(state[CURRENT_LEVEL_INPUT_KEY], 3)
        self.assertEqual(state[START_DATE_INPUT_KEY], TODAY)
        self.assertEqual(
            [
                state[get_available_minutes_input_key(day_offset)]
                for day_offset in range(7)
            ],
            [50, 50, 40, 60, 40, 60, 45],
        )
        self.assertNotIn("generated_plan", state)
        self.assertEqual(state["unrelated"], "keep")

    def test_source_review_sample_uses_text_without_generating(self):
        state = {
            RESULT_STATE_KEY: {"content": "이전 결과"},
            "unrelated": "keep",
        }

        target, _ = apply_sample_input(
            state,
            SAMPLE_SOURCE_REVIEW,
            TODAY,
        )

        self.assertEqual(target, "AI 복습 자료 만들기")
        self.assertEqual(state[VIEW_MODE_KEY], "create")
        self.assertEqual(state[SOURCE_TYPE_KEY], "text")
        self.assertTrue(state[TITLE_KEY])
        self.assertGreater(len(state[TEXT_KEY]), 200)
        self.assertNotIn(RESULT_STATE_KEY, state)
        self.assertEqual(state["unrelated"], "keep")

    def test_tutor_sample_resets_only_tutor_state(self):
        state = {
            "tutor_active_session_id": "old-session",
            "saved_plan_selected_id": "keep-plan",
        }

        target, _ = apply_sample_input(state, SAMPLE_TUTOR, TODAY)

        self.assertEqual(target, "단계별 힌트 AI 튜터")
        self.assertNotIn("tutor_active_session_id", state)
        self.assertTrue(state[SETUP_QUESTION_KEY])
        self.assertTrue(state[SETUP_ATTEMPT_KEY])
        self.assertEqual(state["saved_plan_selected_id"], "keep-plan")

    def test_weekly_reflection_sample_is_applied_after_plan_selection(self):
        state = {"saved_plan_selected_id": "keep-plan"}

        target, _ = apply_sample_input(
            state,
            SAMPLE_WEEKLY_REFLECTION,
            TODAY,
        )

        self.assertEqual(target, "주간 학습 회고")
        answers = state[SAMPLE_REFLECTION_PENDING_KEY]
        self.assertEqual(
            set(answers),
            {
                "went_well",
                "difficulty",
                "effective_method",
                "improvement_intention",
            },
        )
        self.assertTrue(all(answers.values()))
        self.assertEqual(state["saved_plan_selected_id"], "keep-plan")

    def test_unknown_sample_type_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_sample_input({}, "unknown", TODAY)

    def test_create_plan_input_reset_preserves_other_state(self):
        state = {
            COURSE_NAME_INPUT_KEY: "파이썬",
            STUDY_GOAL_INPUT_KEY: "목표",
            get_available_minutes_input_key(0): 50,
            "unrelated": "keep",
        }

        clear_create_plan_input_state(state)

        self.assertNotIn(COURSE_NAME_INPUT_KEY, state)
        self.assertNotIn(STUDY_GOAL_INPUT_KEY, state)
        self.assertNotIn(get_available_minutes_input_key(0), state)
        self.assertEqual(state["unrelated"], "keep")


if __name__ == "__main__":
    unittest.main()
