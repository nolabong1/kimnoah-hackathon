import unittest
from unittest.mock import patch

from views import focus_sprint_component
from views.focus_sprint_component import (
    apply_focus_completion_request,
    build_focus_sprint_config,
    normalize_focus_timer_state,
)


class FocusSprintTests(unittest.TestCase):
    def test_short_task_uses_estimated_minutes(self):
        config = build_focus_sprint_config(
            {
                "id": "task-1",
                "title": "반복문 핵심 익히기",
                "estimated_minutes": 15,
            }
        )

        self.assertEqual(config["duration_minutes"], 15)
        self.assertEqual(config["duration_seconds"], 900)
        self.assertFalse(config["is_capped"])

    def test_long_task_is_split_into_twenty_five_minute_sprint(self):
        config = build_focus_sprint_config(
            {
                "id": "task-1",
                "title": "미니 프로젝트 만들기",
                "estimated_minutes": 60,
            }
        )

        self.assertEqual(config["duration_minutes"], 25)
        self.assertEqual(config["duration_seconds"], 1500)
        self.assertTrue(config["is_capped"])

    def test_invalid_task_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "예상 학습시간"):
            build_focus_sprint_config(
                {"id": "task-1", "title": "과제", "estimated_minutes": True}
            )

    def test_timer_state_accepts_only_bounded_values(self):
        running = normalize_focus_timer_state(
            {
                "phase": "running",
                "remaining_seconds": 120,
                "target_at_ms": 1234567890,
            },
            duration_seconds=300,
        )
        invalid = normalize_focus_timer_state(
            {
                "phase": "running",
                "remaining_seconds": 999,
                "target_at_ms": 1234567890,
            },
            duration_seconds=300,
        )

        self.assertEqual(running["phase"], "running")
        self.assertEqual(invalid["phase"], "ready")
        self.assertEqual(invalid["remaining_seconds"], 300)

    def test_completed_state_has_no_remaining_time(self):
        completed = normalize_focus_timer_state(
            {
                "phase": "completed",
                "remaining_seconds": 20,
                "target_at_ms": 100,
            },
            duration_seconds=300,
        )

        self.assertEqual(
            completed,
            {
                "phase": "completed",
                "remaining_seconds": 0,
                "target_at_ms": None,
            },
        )

    def test_completion_request_opens_only_matching_task_stage(self):
        state = {
            "focus-task-1": {
                "ready_to_complete_task_id": "task-1",
            },
            "dashboard_task_stage_task-1": "content",
            "unrelated": "preserved",
        }

        changed = apply_focus_completion_request(
            state,
            component_key="focus-task-1",
            stage_key="dashboard_task_stage_task-1",
            expected_task_id="task-1",
        )

        self.assertTrue(changed)
        self.assertEqual(
            state["dashboard_task_stage_task-1"],
            "complete",
        )
        self.assertEqual(state["unrelated"], "preserved")

    def test_completion_request_rejects_other_task(self):
        state = {
            "focus-task-1": {
                "ready_to_complete_task_id": "other-task",
            },
            "dashboard_task_stage_task-1": "content",
        }

        changed = apply_focus_completion_request(
            state,
            component_key="focus-task-1",
            stage_key="dashboard_task_stage_task-1",
            expected_task_id="task-1",
        )

        self.assertFalse(changed)
        self.assertEqual(
            state["dashboard_task_stage_task-1"],
            "content",
        )

    def test_frontend_updates_clock_without_per_second_streamlit_state(self):
        source = focus_sprint_component._FOCUS_SPRINT_JS

        self.assertIn("window.setInterval(render, 250)", source)
        self.assertIn('setStateValue("timer", nextTimer)', source)
        self.assertEqual(source.count('setStateValue("timer"'), 1)
        self.assertIn(
            'setTriggerValue("ready_to_complete_task_id"',
            source,
        )
        self.assertIn("window.clearInterval", source)
        self.assertIn("return () =>", source)

    def test_component_is_safe_and_does_not_complete_tasks_or_award_exp(self):
        source = focus_sprint_component._FOCUS_SPRINT_JS
        html = focus_sprint_component._FOCUS_SPRINT_HTML

        self.assertIn("textContent", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("complete_study_task", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)
        self.assertIn("EXP가 지급되지 않습니다", html)
        self.assertIn(
            "prefers-reduced-motion",
            focus_sprint_component._FOCUS_SPRINT_CSS,
        )

    def test_unregistered_component_falls_back_without_breaking_page(self):
        with patch.object(
            focus_sprint_component,
            "_FOCUS_SPRINT",
            side_effect=ValueError(
                "Component 'task_focus_sprint' is not registered"
            ),
        ):
            with patch.object(
                focus_sprint_component.st,
                "session_state",
                {},
            ):
                result = focus_sprint_component.render_focus_sprint(
                    {
                        "id": "task-1",
                        "title": "과제",
                        "estimated_minutes": 10,
                    },
                    key="focus-task-1",
                )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
