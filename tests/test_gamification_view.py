import unittest
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from views.gamification_state import ACTIVE_TAB_KEY


USER_ID = "00000000-0000-0000-0000-000000000001"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def order(self, _field, desc=False):
        del desc
        return self

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, *, rpc_results=None):
        self.rpc_results = rpc_results or {}
        self.rpc_calls = []
        self.table_calls = []

    def table(self, table_name):
        self.table_calls.append(table_name)
        return FakeRequest([])

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        return FakeRequest(self.rpc_results[function_name])


def render_gamification_test_page(supabase, user):
    from views.gamification_view import render_gamification_page

    render_gamification_page(supabase, user)


def render_gamification_summary_test_page(supabase, user_id):
    from views.gamification_view import (
        render_gamification_dashboard_summary,
    )

    render_gamification_dashboard_summary(supabase, user_id)


class GamificationViewTests(unittest.TestCase):
    def test_initial_page_render_is_read_only(self):
        supabase = FakeSupabase()
        user = SimpleNamespace(id=USER_ID)

        app = AppTest.from_function(
            render_gamification_test_page,
            args=(supabase, user),
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(supabase.rpc_calls, [])
        self.assertEqual(
            [tab.label for tab in app.tabs],
            [
                "도전과제",
                "업적",
                "배지 보관함",
            ],
        )
        self.assertEqual(app.session_state[ACTIVE_TAB_KEY], "도전과제")
        self.assertIn(
            "학습 기록 새로 반영하기",
            [button.label for button in app.button],
        )
        self.assertEqual(
            supabase.table_calls,
            [
                "user_achievements",
                "user_challenges",
                "user_badge_showcase",
            ],
        )

        achievement_filter = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "업적 카테고리"
        )
        app = achievement_filter.select("과제").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(supabase.table_calls), 3)

    def test_explicit_sync_button_calls_rpc_once(self):
        supabase = FakeSupabase(
            rpc_results={
                "sync_gamification_state": {
                    "total_exp": 100,
                    "level": 2,
                    "current_streak": 1,
                    "achievement_exp_awarded": 0,
                    "newly_unlocked": [],
                    "newly_completed_challenges": [],
                }
            }
        )
        user = SimpleNamespace(id=USER_ID)
        app = AppTest.from_function(
            render_gamification_test_page,
            args=(supabase, user),
        ).run()

        sync_button = next(
            button
            for button in app.button
            if button.label == "학습 기록 새로 반영하기"
        )
        app = sync_button.click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            supabase.rpc_calls,
            [("sync_gamification_state", {})],
        )
        self.assertIn(
            "현재 학습 기록을 업적과 도전과제에 반영했습니다.",
            [message.value for message in app.success],
        )

    def test_active_badge_tab_is_preserved_across_rerun(self):
        supabase = FakeSupabase()
        user = SimpleNamespace(id=USER_ID)
        app = AppTest.from_function(
            render_gamification_test_page,
            args=(supabase, user),
        ).run()

        app.session_state[ACTIVE_TAB_KEY] = "배지 보관함"
        app = app.run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state[ACTIVE_TAB_KEY],
            "배지 보관함",
        )
        self.assertEqual(len(supabase.table_calls), 3)

    def test_dashboard_summary_is_read_only(self):
        supabase = FakeSupabase()

        app = AppTest.from_function(
            render_gamification_summary_test_page,
            args=(supabase, USER_ID),
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(supabase.rpc_calls, [])
        self.assertIn(
            "업적·도전과제 보기",
            [button.label for button in app.button],
        )


if __name__ == "__main__":
    unittest.main()
