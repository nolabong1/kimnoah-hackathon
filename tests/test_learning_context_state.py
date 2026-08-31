import unittest

from views.learning_context_state import (
    PENDING_NAVIGATION_KEY,
    PLAN_ID_KEY,
    SOURCE_KEY,
    TASK_ID_KEY,
    TUTOR_PAGE_TITLE,
    clear_learning_context,
    get_learning_context,
    has_learning_context,
    request_tutor_learning_context,
)


class LearningContextStateTests(unittest.TestCase):
    def test_tutor_request_keeps_plan_task_and_navigation_together(self):
        state = {}

        request_tutor_learning_context(
            state,
            plan_id="plan-1",
            task_id="task-1",
            source="today",
        )

        self.assertEqual(state[PLAN_ID_KEY], "plan-1")
        self.assertEqual(state[TASK_ID_KEY], "task-1")
        self.assertEqual(state[SOURCE_KEY], "today")
        self.assertEqual(
            state[PENDING_NAVIGATION_KEY],
            TUTOR_PAGE_TITLE,
        )
        self.assertEqual(
            get_learning_context(state),
            ("plan-1", "task-1", "today"),
        )
        self.assertTrue(has_learning_context(state))

    def test_missing_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            request_tutor_learning_context(
                {},
                plan_id="plan-1",
                task_id=" ",
                source="saved_plan",
            )

    def test_clear_removes_only_learning_context_keys(self):
        state = {
            PLAN_ID_KEY: "plan-1",
            TASK_ID_KEY: "task-1",
            SOURCE_KEY: "today",
            PENDING_NAVIGATION_KEY: TUTOR_PAGE_TITLE,
            "tutor_active_session_id": "keep-tutor",
            "dashboard_selected_plan_id": "keep-plan",
        }

        clear_learning_context(state)

        self.assertFalse(has_learning_context(state))
        self.assertNotIn(PENDING_NAVIGATION_KEY, state)
        self.assertEqual(
            state["tutor_active_session_id"],
            "keep-tutor",
        )
        self.assertEqual(
            state["dashboard_selected_plan_id"],
            "keep-plan",
        )


if __name__ == "__main__":
    unittest.main()
