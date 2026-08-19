import unittest

from views import study_room_editor_component


class StudyRoomEditorComponentTests(unittest.TestCase):
    def test_component_uses_v2_state_api_and_pointer_interactions(self):
        source = study_room_editor_component._EDITOR_JS

        self.assertIn("setStateValue", source)
        self.assertIn("pointermove", source)
        self.assertIn('mode === "move"', source)
        self.assertIn('mode === "scale"', source)
        self.assertIn('mode === "rotate"', source)
        self.assertIn("flip_horizontal", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)

    def test_component_emits_only_after_pointer_interaction_finishes(self):
        source = study_room_editor_component._EDITOR_JS
        move_start = source.index("const onMove")
        finish_start = source.index("const finish", move_start)
        move_block = source[move_start:finish_start]
        finish_block = source[
            finish_start:source.index("state.cleanupPointer = () =>", finish_start)
        ]

        self.assertNotIn("emitTransforms()", move_block)
        self.assertIn("emitTransforms()", finish_block)


if __name__ == "__main__":
    unittest.main()
