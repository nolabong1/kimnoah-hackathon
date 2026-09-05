import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from views.test_tools_view import (
    ACCESS_ALLOWED_KEY,
    ACCESS_CHECKED_KEY,
    PENDING_NAVIGATION_KEY,
    SAMPLE_INPUT_SELECT_KEY,
    STREAK_PREVIEW_KEY,
    TEST_TOOLS_EXPANDER_KEY,
    build_streak_preview_profile,
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
        profile={"current_streak": 2},
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

    def test_access_state_is_removed_with_other_test_tool_state(self):
        state = {
            ACCESS_CHECKED_KEY: True,
            ACCESS_ALLOWED_KEY: True,
            "unrelated_state": "kept",
        }

        clear_test_tools_state(state)

        self.assertNotIn(ACCESS_CHECKED_KEY, state)
        self.assertNotIn(ACCESS_ALLOWED_KEY, state)
        self.assertEqual(state["unrelated_state"], "kept")

    def test_streak_preview_changes_only_display_profile(self):
        profile = {
            "nickname": "테스터",
            "current_streak": 2,
            "total_exp": 100,
        }
        state = {
            ACCESS_ALLOWED_KEY: True,
            STREAK_PREVIEW_KEY: 7,
        }

        preview = build_streak_preview_profile(profile, state)

        self.assertEqual(preview["current_streak"], 7)
        self.assertEqual(preview["total_exp"], 100)
        self.assertEqual(profile["current_streak"], 2)

    def test_streak_preview_requires_access_and_known_preset(self):
        profile = {"current_streak": 2}

        unauthorized = build_streak_preview_profile(
            profile,
            {STREAK_PREVIEW_KEY: 30},
        )
        invalid = build_streak_preview_profile(
            profile,
            {
                ACCESS_ALLOWED_KEY: True,
                STREAK_PREVIEW_KEY: 999,
            },
        )
        boolean_value = build_streak_preview_profile(
            profile,
            {
                ACCESS_ALLOWED_KEY: True,
                STREAK_PREVIEW_KEY: True,
            },
        )

        self.assertEqual(unauthorized["current_streak"], 2)
        self.assertEqual(invalid["current_streak"], 2)
        self.assertEqual(boolean_value["current_streak"], 2)


class TestToolsLayoutTests(unittest.TestCase):
    def test_closed_sidebar_tool_does_not_load_plans(self):
        with (
            patch(
                "views.test_tools_view.can_use_test_tools",
                return_value=True,
            ),
            patch(
                "views.test_tools_view.get_user_study_plans"
            ) as get_plans,
        ):
            app = AppTest.from_function(
                render_test_tools_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        get_plans.assert_not_called()

    def test_unauthorized_user_does_not_see_test_tools(self):
        with (
            patch(
                "views.test_tools_view.can_use_test_tools",
                return_value=False,
            ) as access_check,
            patch(
                "views.test_tools_view.get_user_study_plans"
            ) as get_plans,
        ):
            app = AppTest.from_function(
                render_test_tools_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.sidebar.expander), [])
        access_check.assert_called_once()
        get_plans.assert_not_called()

    def test_access_check_failure_hides_test_tools(self):
        with patch(
            "views.test_tools_view.can_use_test_tools",
            side_effect=RuntimeError("missing migration"),
        ):
            app = AppTest.from_function(
                render_test_tools_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.sidebar.expander), [])

    def test_open_sidebar_tool_contains_learning_and_shop_test_actions(self):
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
                "views.test_tools_view.can_use_test_tools",
                return_value=True,
            ),
            patch(
                "views.test_tools_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.test_tools_view.get_study_plan_tasks",
                return_value=[task],
            ),
            patch(
                "views.test_tools_view.get_active_shop_test_session",
                return_value=None,
            ),
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        button_labels = [button.label for button in app.sidebar.button]
        self.assertIn("오늘 테스트 기록 초기화", button_labels)
        self.assertIn("이번 주 계획 완료 처리", button_labels)
        self.assertIn("상점 테스트 시작", button_labels)
        self.assertIn("선택한 샘플 입력 채우기", button_labels)
        self.assertTrue(
            any(
                selectbox.label == "샘플을 채울 기능"
                for selectbox in app.sidebar.selectbox
            )
        )
        self.assertTrue(
            any(
                selectbox.label == "미리 볼 연속 학습일"
                for selectbox in app.sidebar.selectbox
            )
        )

    def test_active_shop_test_session_shows_reset_action(self):
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
        active_session = {
            "id": "33333333-3333-4333-8333-333333333333",
            "credit_amount": 1200,
            "started_at": "2026-08-19T10:00:00+00:00",
        }
        app = AppTest.from_function(
            render_test_tools_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )
        app.session_state[TEST_TOOLS_EXPANDER_KEY] = True

        with (
            patch(
                "views.test_tools_view.can_use_test_tools",
                return_value=True,
            ),
            patch(
                "views.test_tools_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.test_tools_view.get_study_plan_tasks",
                return_value=[task],
            ),
            patch(
                "views.test_tools_view.get_active_shop_test_session",
                return_value=active_session,
            ),
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        button_labels = [button.label for button in app.sidebar.button]
        self.assertIn("상점 테스트 초기화", button_labels)

    def test_sample_button_fills_input_and_requests_target_navigation(self):
        from views.source_review_material_view import TEXT_KEY, TITLE_KEY

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
                "views.test_tools_view.can_use_test_tools",
                return_value=True,
            ),
            patch(
                "views.test_tools_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.test_tools_view.get_study_plan_tasks",
                return_value=[task],
            ),
            patch(
                "views.test_tools_view.get_active_shop_test_session",
                return_value=None,
            ),
        ):
            app.run()
            app.selectbox(key=SAMPLE_INPUT_SELECT_KEY).set_value(
                "source_review"
            ).run()
            app.button(key="test_tools_apply_sample_input").click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state[PENDING_NAVIGATION_KEY],
            "AI 복습 자료 만들기",
        )
        self.assertTrue(app.session_state[TITLE_KEY])
        self.assertGreater(len(app.session_state[TEXT_KEY]), 200)

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
