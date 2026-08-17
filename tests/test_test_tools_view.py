import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from views.test_tools_view import (
    TEST_TOOLS_EXPANDER_KEY,
    clear_test_tools_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"


def render_test_tools_page(supabase, user):
    from views.test_tools_view import render_sidebar_test_tools

    render_sidebar_test_tools(
        supabase=supabase,
        user=user,
    )


class TestToolsStateTests(unittest.TestCase):
    def test_clear_removes_only_test_tool_state(self):
        state = {
            TEST_TOOLS_EXPANDER_KEY: True,
            "test_tools_plan_id": PLAN_ID,
            "weekly_review_selected_plan_id": PLAN_ID,
            "saved_plan_selected_id": PLAN_ID,
        }

        clear_test_tools_state(state)

        self.assertNotIn(TEST_TOOLS_EXPANDER_KEY, state)
        self.assertNotIn("test_tools_plan_id", state)
        self.assertEqual(state["weekly_review_selected_plan_id"], PLAN_ID)
        self.assertEqual(state["saved_plan_selected_id"], PLAN_ID)


class TestToolsLayoutTests(unittest.TestCase):
    def test_closed_sidebar_tool_does_not_load_plans(self):
        with patch(
            "views.test_tools_view.get_user_study_plans"
        ) as get_plans:
            app = AppTest.from_function(
                render_test_tools_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        get_plans.assert_not_called()

    def test_open_sidebar_tool_contains_both_test_actions(self):
        plan = {
            "id": PLAN_ID,
            "title": "파이썬 테스트 계획",
            "start_date": "2026-08-17",
        }
        task = {
            "id": "task-1",
            "status": "pending",
            "task_type": "learn",
        }
        app = AppTest.from_function(
            render_test_tools_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )
        app.session_state[TEST_TOOLS_EXPANDER_KEY] = True

        with (
            patch(
                "views.test_tools_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.test_tools_view.get_study_plan_tasks",
                return_value=[task],
            ),
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        button_labels = [button.label for button in app.sidebar.button]
        self.assertIn("오늘 테스트 기록 초기화", button_labels)
        self.assertIn("이번 주 계획 완료 처리", button_labels)

    def test_page_views_no_longer_render_test_buttons(self):
        saved_plan_source = (
            PROJECT_ROOT / "views" / "saved_plans_view.py"
        ).read_text(encoding="utf-8")
        weekly_review_source = (
            PROJECT_ROOT / "views" / "weekly_review_view.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("오늘 테스트 기록 초기화", saved_plan_source)
        self.assertNotIn("이번 주 계획 완료 처리", weekly_review_source)


if __name__ == "__main__":
    unittest.main()
