import unittest

from services.study_room_service import empty_study_room_transforms
from views import study_room_editor_component
from views.shop_state import (
    pop_room_save_reveal,
    queue_room_save_reveal,
)
from views.study_room_view import build_study_room_save_feedback


NOW = "2026-09-01T13:40:00+00:00"


def _equipment(*, desk: str | None = "desk_oak_basic") -> dict:
    return {
        "background_item_key": None,
        "floor_item_key": None,
        "desk_item_key": desk,
        "chair_item_key": None,
        "decor_left_item_key": "decor_green_plant",
        "decor_right_item_key": None,
        "accent_item_key": None,
    }


def _saved_room() -> dict:
    transforms = empty_study_room_transforms()
    transforms["desk"]["x"] = 30
    return {
        "user_id": "00000000-0000-0000-0000-000000000001",
        **_equipment(),
        "item_transforms": transforms,
        "created_at": NOW,
        "updated_at": NOW,
    }


class StudyRoomSaveFeedbackTests(unittest.TestCase):
    def test_feedback_summarizes_server_confirmed_room_changes(self):
        feedback = build_study_room_save_feedback(
            _saved_room(),
            _equipment(desk=None),
            empty_study_room_transforms(),
        )

        self.assertEqual(feedback["event_id"], NOW)
        self.assertEqual(feedback["equipped_count"], 2)
        self.assertEqual(feedback["changed_slot_count"], 1)
        self.assertTrue(feedback["placement_changed"])
        self.assertIn("슬롯 1개 변경", feedback["message"])
        self.assertIn("가구 배치 반영", feedback["message"])

    def test_feedback_is_consumed_exactly_once(self):
        state = {}
        feedback = build_study_room_save_feedback(
            _saved_room(),
            _equipment(desk=None),
            empty_study_room_transforms(),
        )

        queue_room_save_reveal(state, feedback)

        self.assertEqual(pop_room_save_reveal(state), feedback)
        self.assertIsNone(pop_room_save_reveal(state))

    def test_save_feedback_does_not_emit_database_or_streamlit_events(self):
        source = study_room_editor_component._EDITOR_JS
        start = source.index("const revealSaveFeedback")
        end = source.index("renderAll()", start)
        feedback_block = source[start:end]

        self.assertNotIn("setStateValue", feedback_block)
        self.assertNotIn("setTriggerValue", feedback_block)
        self.assertNotIn("fetch(", feedback_block)
        self.assertNotIn("postMessage", feedback_block)


if __name__ == "__main__":
    unittest.main()
