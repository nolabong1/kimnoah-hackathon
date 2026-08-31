import unittest
from unittest.mock import patch

from views import learning_quest_map_component
from views.learning_quest_map_component import (
    apply_quest_map_selection,
    build_learning_quest_nodes,
)


class LearningQuestMapTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [
            {
                "id": "task-1",
                "title": "핵심 개념 익히기",
                "task_type": "learn",
                "estimated_minutes": 25,
                "status": "completed",
            },
            {
                "id": "task-2",
                "title": "개념 복습하기",
                "task_type": "review",
                "estimated_minutes": 15,
                "status": "pending",
            },
        ]

    def test_nodes_keep_task_order_and_selection(self):
        nodes = build_learning_quest_nodes(self.tasks, "task-2")

        self.assertEqual([node["id"] for node in nodes], ["task-1", "task-2"])
        self.assertEqual([node["step"] for node in nodes], [1, 2])
        self.assertTrue(nodes[0]["completed"])
        self.assertFalse(nodes[0]["selected"])
        self.assertTrue(nodes[1]["selected"])
        self.assertEqual(nodes[1]["task_type_label"], "복습")

    def test_unknown_selected_task_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "오늘 퀘스트"):
            build_learning_quest_nodes(self.tasks, "other-task")

    def test_duplicate_task_ids_are_rejected(self):
        duplicate_tasks = [self.tasks[0], dict(self.tasks[0])]

        with self.assertRaisesRegex(ValueError, "중복"):
            build_learning_quest_nodes(duplicate_tasks, "task-1")

    def test_component_selection_updates_only_allowed_task(self):
        state = {
            "quest-map": {"selected_task_id": "task-2"},
            "dashboard_selected_task_id": "task-1",
            "unrelated": "preserved",
        }

        changed = apply_quest_map_selection(
            state,
            component_key="quest-map",
            selection_key="dashboard_selected_task_id",
            allowed_task_ids=["task-1", "task-2"],
        )

        self.assertTrue(changed)
        self.assertEqual(state["dashboard_selected_task_id"], "task-2")
        self.assertEqual(state["unrelated"], "preserved")

    def test_component_selection_rejects_untrusted_task_id(self):
        state = {
            "quest-map": {"selected_task_id": "other-user-task"},
            "dashboard_selected_task_id": "task-1",
        }

        changed = apply_quest_map_selection(
            state,
            component_key="quest-map",
            selection_key="dashboard_selected_task_id",
            allowed_task_ids=["task-1", "task-2"],
        )

        self.assertFalse(changed)
        self.assertEqual(state["dashboard_selected_task_id"], "task-1")

    def test_component_uses_v2_trigger_and_safe_dom_updates(self):
        source = learning_quest_map_component._QUEST_MAP_JS

        self.assertIn('setTriggerValue("selected_task_id"', source)
        self.assertIn("textContent", source)
        self.assertIn("replaceChildren", source)
        self.assertIn("return () =>", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)

    def test_component_supports_reduced_motion(self):
        self.assertIn(
            "prefers-reduced-motion",
            learning_quest_map_component._QUEST_MAP_CSS,
        )

    def test_unregistered_component_falls_back_without_breaking_page(self):
        with patch.object(
            learning_quest_map_component,
            "_LEARNING_QUEST_MAP",
            side_effect=ValueError(
                "Component 'learning_quest_map' is not registered"
            ),
        ):
            result = learning_quest_map_component.render_learning_quest_map(
                [],
                key="quest-map",
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
