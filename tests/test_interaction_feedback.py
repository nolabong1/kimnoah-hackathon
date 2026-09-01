import unittest

from views import interaction_feedback_component
from views.interaction_feedback import (
    _build_gamification_events,
    order_interaction_events,
)
from views.interaction_state import (
    INTERACTION_QUEUE_KEY,
    clear_interaction_state,
    defer_completion_interaction_events,
    pop_completion_interaction_events,
    pop_interaction_events,
    queue_challenge_reward_interaction,
    queue_level_up_interaction,
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

    def test_new_challenge_reward_is_queued_once(self):
        state = {}
        result = {
            "challenge_id": "challenge-1",
            "reward_exp": 15,
            "total_exp": 215,
            "level": 3,
            "already_claimed": False,
        }

        queue_challenge_reward_interaction(state, result)
        events = pop_interaction_events(state)
        queue_challenge_reward_interaction(state, result)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "challenge_reward_claimed")
        self.assertEqual(events[0]["value"], "+15 EXP")
        self.assertIn("총 EXP 215", events[0]["message"])
        self.assertNotIn(INTERACTION_QUEUE_KEY, state)

    def test_duplicate_challenge_claim_does_not_create_feedback(self):
        state = {}

        queue_challenge_reward_interaction(
            state,
            {
                "challenge_id": "challenge-1",
                "reward_exp": 0,
                "total_exp": 215,
                "level": 3,
                "already_claimed": True,
            },
        )

        self.assertEqual(state, {})

    def test_task_reward_crossing_exp_boundary_queues_level_up(self):
        state = {}

        queue_task_completion_interactions(
            state,
            task_id="task-level-up",
            result={
                "already_completed": False,
                "task_exp": 10,
                "daily_bonus_exp": 0,
                "total_exp": 105,
                "level": 2,
                "gamification": {"achievement_exp_awarded": 0},
            },
        )

        self.assertEqual(
            [event["kind"] for event in state[INTERACTION_QUEUE_KEY]],
            ["task_complete", "level_up"],
        )
        self.assertEqual(
            state[INTERACTION_QUEUE_KEY][-1]["value"],
            "Lv.1 → Lv.2",
        )

    def test_task_level_up_includes_achievement_exp_awarded_together(self):
        state = {}

        queue_task_completion_interactions(
            state,
            task_id="task-achievement-level-up",
            result={
                "already_completed": False,
                "task_exp": 10,
                "daily_bonus_exp": 0,
                "total_exp": 210,
                "level": 3,
                "gamification": {"achievement_exp_awarded": 15},
            },
        )

        self.assertEqual(
            [event["kind"] for event in state[INTERACTION_QUEUE_KEY]],
            ["task_complete", "level_up"],
        )
        self.assertEqual(
            state[INTERACTION_QUEUE_KEY][-1]["value"],
            "Lv.2 → Lv.3",
        )

    def test_level_up_requires_matching_server_level_and_exp_boundary(self):
        state = {}

        queue_level_up_interaction(
            state,
            event_source="challenge:one",
            total_exp=205,
            awarded_exp=10,
            level=2,
        )
        queue_level_up_interaction(
            state,
            event_source="challenge:two",
            total_exp=215,
            awarded_exp=15,
            level=3,
        )

        self.assertEqual(state, {})

    def test_challenge_reward_can_queue_reward_and_level_up(self):
        state = {}

        queue_challenge_reward_interaction(
            state,
            {
                "challenge_id": "challenge-level-up",
                "reward_exp": 10,
                "total_exp": 205,
                "level": 3,
                "already_claimed": False,
            },
        )

        self.assertEqual(
            [event["kind"] for event in state[INTERACTION_QUEUE_KEY]],
            ["challenge_reward_claimed", "level_up"],
        )

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

    def test_level_up_is_ordered_after_achievement_unlock(self):
        events = order_interaction_events(
            [
                {
                    "event_id": "task_complete:task-1",
                    "kind": "task_complete",
                    "tone": "success",
                    "title": "과제 완료!",
                    "message": "학습 기록이 저장되었습니다.",
                    "value": "+10 EXP",
                    "icon": "✓",
                },
                {
                    "event_id": "level_up:task:task-1:2",
                    "kind": "level_up",
                    "tone": "level",
                    "title": "레벨 2 달성!",
                    "message": "누적 EXP 105",
                    "value": "Lv.1 → Lv.2",
                    "icon": "▲",
                },
            ],
            [
                {
                    "achievement_key": "first_task_completed",
                    "reward_exp": 10,
                }
            ],
        )

        self.assertEqual(
            [event["kind"] for event in events],
            ["task_complete", "achievement_unlock", "level_up"],
        )


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

    def test_level_up_uses_a_distinct_theme_tone(self):
        css = interaction_feedback_component._FEEDBACK_CSS

        self.assertIn('data-tone="level"', css)


if __name__ == "__main__":
    unittest.main()
