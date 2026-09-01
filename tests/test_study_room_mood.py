import unittest

from views import study_room_editor_component
from views.study_room_editor_component import build_study_room_mood


class StudyRoomMoodTests(unittest.TestCase):
    def test_streak_selects_deterministic_room_mood(self):
        cases = [
            (0, "ready"),
            (1, "spark"),
            (3, "growing"),
            (7, "strong"),
            (14, "blazing"),
            (30, "legendary"),
        ]

        for streak, expected_tier in cases:
            with self.subTest(streak=streak):
                mood = build_study_room_mood(
                    {"level": 4, "current_streak": streak}
                )
                self.assertEqual(mood["tier"], expected_tier)
                self.assertEqual(mood["level"], 4)
                self.assertEqual(mood["current_streak"], streak)
                self.assertTrue(mood["tier_label"])

    def test_invalid_profile_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "레벨"):
            build_study_room_mood({"level": 0, "current_streak": 1})
        with self.assertRaisesRegex(ValueError, "연속 학습일"):
            build_study_room_mood({"level": 1, "current_streak": -1})

    def test_encouragement_stays_inside_component_without_streamlit_event(self):
        source = study_room_editor_component._EDITOR_JS
        encouragement = source[
            source.index("encourageButton.onclick") : source.index(
                "renderAll()",
                source.index("encourageButton.onclick"),
            )
        ]

        self.assertIn("room-spark", encouragement)
        self.assertIn("window.setTimeout", encouragement)
        self.assertNotIn("setStateValue", encouragement)
        self.assertNotIn("setTriggerValue", encouragement)


if __name__ == "__main__":
    unittest.main()
