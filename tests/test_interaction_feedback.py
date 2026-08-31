import unittest

from views import interaction_feedback_component
from views.interaction_feedback import _build_gamification_events
from views.interaction_state import (
    INTERACTION_QUEUE_KEY,
    clear_interaction_state,
    defer_completion_interaction_events,
    pop_completion_interaction_events,
    pop_interaction_events,
    queue_quiz_result_interaction,
    queue_task_completion_interactions,
)


class InteractionStateTests(unittest.TestCase):
    def test_task_and_daily_bonus_events_are_queued_once(self):
        state = {}
        result = {
            "already_completed": False,
            "task_exp": 10,
            "daily_bonus_exp": 20,
            "total_exp": 130,
        }

        queue_task_completion_interactions(
            state,
            task_id="task-1",
            result=result,
        )

        self.assertEqual(
            [event["kind"] for event in state[INTERACTION_QUEUE_KEY]],
            ["task_complete", "daily_bonus"],
        )
        events = pop_interaction_events(state)
        self.assertEqual([event["value"] for event in events], ["+10 EXP", "+20 EXP"])

        queue_task_completion_interactions(
            state,
            task_id="task-1",
            result=result,
        )
        self.assertNotIn(INTERACTION_QUEUE_KEY, state)

    def test_already_completed_task_does_not_create_feedback(self):
        state = {}

        queue_task_completion_interactions(
            state,
            task_id="task-1",
            result={
                "already_completed": True,
                "task_exp": 0,
                "daily_bonus_exp": 0,
                "total_exp": 130,
            },
        )

        self.assertEqual(state, {})

    def test_quiz_result_uses_attempt_id_for_replay_protection(self):
        state = {}
        attempt = {"attempt_id": "attempt-1", "score": 100}

        queue_quiz_result_interaction(state, attempt)
        first_events = pop_interaction_events(state)
        queue_quiz_result_interaction(state, attempt)

        self.assertEqual(len(first_events), 1)
        self.assertEqual(first_events[0]["title"], "퀴즈 만점!")
        self.assertEqual(first_events[0]["value"], "100점")
        self.assertNotIn(INTERACTION_QUEUE_KEY, state)

    def test_clear_removes_only_interaction_state(self):
        state = {
            "interaction_event_queue": [{"event_id": "one"}],
            "interaction_seen_event_ids": ["one"],
            "gamification_success_message": "보존",
            "auth_user": "user-1",
        }

        clear_interaction_state(state)

        self.assertEqual(
            state,
            {
                "gamification_success_message": "보존",
                "auth_user": "user-1",
            },
        )

    def test_completion_events_are_deferred_and_popped_once(self):
        state = {}
        queue_task_completion_interactions(
            state,
            task_id="task-1",
            result={
                "already_completed": False,
                "task_exp": 10,
                "daily_bonus_exp": 20,
                "total_exp": 130,
            },
        )
        events = pop_interaction_events(state)

        defer_completion_interaction_events(state, events)

        self.assertEqual(
            [event["kind"] for event in pop_completion_interaction_events(state)],
            ["task_complete", "daily_bonus"],
        )
        self.assertEqual(pop_completion_interaction_events(state), [])


class GamificationInteractionTests(unittest.TestCase):
    def test_known_achievement_and_challenge_become_feedback_events(self):
        events = _build_gamification_events(
            [
                {
                    "achievement_key": "first_task_completed",
                    "reward_exp": 10,
                },
                {
                    "challenge_id": "challenge-1",
                    "template_key": "daily_complete_1_task",
                },
            ]
        )

        self.assertEqual(
            [event["kind"] for event in events],
            ["achievement_unlock", "challenge_complete"],
        )
        self.assertIn("+10 EXP", events[0]["value"])
        self.assertEqual(events[1]["value"], "보상 수령 가능")

    def test_unknown_catalog_entries_are_ignored(self):
        events = _build_gamification_events(
            [
                {"achievement_key": "unknown", "reward_exp": 10},
                {
                    "challenge_id": "challenge-1",
                    "template_key": "unknown",
                },
            ]
        )

        self.assertEqual(events, [])


class InteractionComponentTests(unittest.TestCase):
    def test_component_uses_v2_and_safe_text_rendering(self):
        source = interaction_feedback_component._FEEDBACK_JS

        self.assertIn("textContent", source)
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn("return () =>", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)

    def test_overlay_does_not_block_the_page_and_can_be_skipped(self):
        css = interaction_feedback_component._FEEDBACK_CSS
        javascript = interaction_feedback_component._FEEDBACK_JS

        self.assertIn("pointer-events: none", css)
        self.assertIn("skip.onclick = finish", javascript)
        self.assertIn("clearTimers()", javascript)

    def test_inline_mode_stays_inside_the_completion_dialog(self):
        css = interaction_feedback_component._FEEDBACK_CSS
        javascript = interaction_feedback_component._FEEDBACK_JS

        self.assertIn('[data-placement="inline"]', css)
        self.assertIn('data?.placement === "inline"', javascript)
        self.assertIn("position: relative", css)


if __name__ == "__main__":
    unittest.main()
