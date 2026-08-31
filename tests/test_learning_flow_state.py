import unittest

from views.learning_flow_state import (
    TASK_STAGE_COMPLETE,
    TASK_STAGE_CONTENT,
    TASK_STAGE_OVERVIEW,
    get_default_task_stage,
    get_next_pending_task_id,
    get_task_stage_key,
    get_task_stage_label,
)


class LearningFlowStateTests(unittest.TestCase):
    def test_pending_task_starts_with_overview(self):
        self.assertEqual(
            get_default_task_stage({"status": "pending"}),
            TASK_STAGE_OVERVIEW,
        )

    def test_completed_task_starts_with_completion(self):
        self.assertEqual(
            get_default_task_stage({"status": "completed"}),
            TASK_STAGE_COMPLETE,
        )

    def test_content_label_matches_task_type(self):
        self.assertIn(
            "AI 학습자료",
            get_task_stage_label(TASK_STAGE_CONTENT, "learn"),
        )
        self.assertIn(
            "AI 퀴즈",
            get_task_stage_label(TASK_STAGE_CONTENT, "quiz"),
        )

    def test_next_pending_task_uses_following_order(self):
        tasks = [
            {"id": "first", "status": "pending"},
            {"id": "current", "status": "pending"},
            {"id": "done", "status": "completed"},
            {"id": "next", "status": "pending"},
        ]

        self.assertEqual(
            get_next_pending_task_id(tasks, "current"),
            "next",
        )

    def test_next_pending_task_wraps_once(self):
        tasks = [
            {"id": "first", "status": "pending"},
            {"id": "done", "status": "completed"},
            {"id": "current", "status": "pending"},
        ]

        self.assertEqual(
            get_next_pending_task_id(tasks, "current"),
            "first",
        )

    def test_no_other_pending_task_returns_none(self):
        tasks = [
            {"id": "done", "status": "completed"},
            {"id": "current", "status": "pending"},
        ]

        self.assertIsNone(
            get_next_pending_task_id(tasks, "current")
        )

    def test_stage_key_is_scoped_to_task(self):
        self.assertEqual(
            get_task_stage_key("dashboard", "task-1"),
            "dashboard_task_stage_task-1",
        )


if __name__ == "__main__":
    unittest.main()
