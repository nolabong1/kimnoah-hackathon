import unittest
from unittest.mock import patch

from views import learning_momentum_component
from views.learning_momentum_component import build_learning_momentum


class LearningMomentumTests(unittest.TestCase):
    def test_builds_streak_task_and_level_progress(self):
        momentum = build_learning_momentum(
            {
                "total_exp": 235,
                "level": 3,
                "current_streak": 4,
            },
            completed_tasks=2,
            total_tasks=4,
        )

        self.assertEqual(momentum["level_progress_exp"], 35)
        self.assertEqual(momentum["exp_to_next_level"], 65)
        self.assertEqual(momentum["level_progress_percent"], 35)
        self.assertEqual(momentum["today_progress_percent"], 50)
        self.assertEqual(momentum["streak_tier"], "growing")
        self.assertFalse(momentum["today_complete"])

    def test_exact_level_boundary_starts_next_progress_at_zero(self):
        momentum = build_learning_momentum(
            {
                "total_exp": 300,
                "level": 4,
                "current_streak": 7,
            },
            completed_tasks=3,
            total_tasks=3,
        )

        self.assertEqual(momentum["level_progress_exp"], 0)
        self.assertEqual(momentum["exp_to_next_level"], 100)
        self.assertEqual(momentum["streak_tier"], "strong")
        self.assertTrue(momentum["today_complete"])
        self.assertIn("완주", momentum["pace_message"])

    def test_streak_milestones_have_distinct_presentation_tiers(self):
        expected = {
            0: "ready",
            1: "spark",
            3: "growing",
            7: "strong",
            14: "blazing",
            30: "legendary",
        }

        for streak, tier in expected.items():
            with self.subTest(streak=streak):
                momentum = build_learning_momentum(
                    {"total_exp": 0, "level": 1, "current_streak": streak},
                    completed_tasks=0,
                    total_tasks=1,
                )
                self.assertEqual(momentum["streak_tier"], tier)
                self.assertTrue(momentum["streak_tier_label"])

        self.assertIn(
            '[data-tier="blazing"]',
            learning_momentum_component._MOMENTUM_CSS,
        )
        self.assertIn(
            '[data-tier="legendary"]',
            learning_momentum_component._MOMENTUM_CSS,
        )

    def test_invalid_counts_and_profile_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "완료 과제 수"):
            build_learning_momentum(
                {"total_exp": 10, "level": 1, "current_streak": 0},
                completed_tasks=2,
                total_tasks=1,
            )
        with self.assertRaisesRegex(ValueError, "총 EXP"):
            build_learning_momentum(
                {"total_exp": True, "level": 1, "current_streak": 0},
                completed_tasks=0,
                total_tasks=1,
            )

    def test_component_uses_safe_dom_and_respects_reduced_motion(self):
        javascript = learning_momentum_component._MOMENTUM_JS
        css = learning_momentum_component._MOMENTUM_CSS

        self.assertIn("textContent", javascript)
        self.assertNotIn("innerHTML", javascript)
        self.assertNotIn("Streamlit.setComponentValue", javascript)
        self.assertNotIn("window.parent.postMessage", javascript)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("var(--st-primary-color)", css)

    def test_unregistered_component_falls_back_without_breaking_page(self):
        with patch.object(
            learning_momentum_component,
            "_LEARNING_MOMENTUM",
            side_effect=ValueError(
                "Component 'learning_momentum_hud' is not registered"
            ),
        ):
            result = learning_momentum_component.render_learning_momentum(
                {},
                key="momentum",
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
