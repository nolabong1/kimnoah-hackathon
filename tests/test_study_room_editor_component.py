import unittest

from views import study_room_editor_component


class StudyRoomEditorComponentTests(unittest.TestCase):
    def test_character_reactions_follow_learning_streak_tier(self):
        ready = study_room_editor_component.build_study_room_mood(
            {"level": 1, "current_streak": 0}
        )
        strong = study_room_editor_component.build_study_room_mood(
            {"level": 4, "current_streak": 9}
        )

        self.assertEqual(len(ready["character"]["messages"]), 3)
        self.assertIn("첫 과제", ready["character"]["messages"][0])
        self.assertIn("9일", strong["character"]["messages"][0])
        self.assertTrue(strong["character"]["save_message"])

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

    def test_component_receives_transform_limits_from_python_scene(self):
        source = study_room_editor_component._EDITOR_JS

        self.assertIn("resolveLimits(data?.transform_limits)", source)
        self.assertIn("normalizeTransforms(data?.transforms, layers, limits)", source)
        self.assertNotIn("const LIMITS", source)
        self.assertNotIn("|| 1600", source)
        self.assertNotIn("|| 900", source)

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

    def test_equipped_study_cat_reacts_to_tap_without_database_event(self):
        source = study_room_editor_component._EDITOR_JS
        reaction_start = source.index("const revealCharacterReaction")
        reaction_end = source.index(
            "const startPointerInteraction",
            reaction_start,
        )
        reaction_block = source[reaction_start:reaction_end]

        self.assertIn('layer.item_key === "accent_study_cat"', source)
        self.assertIn("maximumPointerDistance <= 12", source)
        self.assertIn('revealCharacterReaction("tap")', source)
        self.assertIn('revealCharacterReaction("save")', source)
        self.assertNotIn("setStateValue", reaction_block)
        self.assertNotIn("setTriggerValue", reaction_block)
        self.assertNotIn("fetch(", reaction_block)

    def test_character_animation_respects_reduced_motion(self):
        css = study_room_editor_component._EDITOR_CSS

        self.assertIn("room-character-breathe", css)
        self.assertIn("room-character-hop", css)
        reduced_motion = css[
            css.index("@media (prefers-reduced-motion: reduce)") :
        ]
        self.assertIn(".room-object.is-character", reduced_motion)

    def test_streak_milestones_change_room_ambience_and_spark_count(self):
        css = study_room_editor_component._EDITOR_CSS
        javascript = study_room_editor_component._EDITOR_JS

        self.assertIn('[data-mood="blazing"]', css)
        self.assertIn('[data-mood="legendary"]', css)
        self.assertIn("blazing: 18", javascript)
        self.assertIn("legendary: 24", javascript)


if __name__ == "__main__":
    unittest.main()
