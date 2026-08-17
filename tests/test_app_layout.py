import ast
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"


def _get_streamlit_call_keywords(function_name: str) -> dict:
    """app.py의 지정 Streamlit 호출에서 고정 키워드 값을 읽습니다."""

    tree = ast.parse(
        (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "st"
            and function.attr == function_name
        ):
            return {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in node.keywords
                if keyword.arg is not None
            }
    raise AssertionError(f"st.{function_name} 호출을 찾지 못했습니다.")


def render_dashboard_test_page(supabase, user):
    from views.dashboard_view import render_dashboard

    render_dashboard(supabase, user)


class AppLayoutTests(unittest.TestCase):
    def test_desktop_layout_uses_wide_expanded_sidebar(self):
        page_config = _get_streamlit_call_keywords("set_page_config")

        self.assertEqual(page_config["layout"], "wide")
        self.assertEqual(page_config["initial_sidebar_state"], "expanded")

    def test_navigation_uses_expanded_sidebar(self):
        navigation = _get_streamlit_call_keywords("navigation")

        self.assertEqual(navigation["position"], "sidebar")
        self.assertTrue(navigation["expanded"])

    def test_dashboard_renders_desktop_summary_and_tasks(self):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        plan = {
            "id": PLAN_ID,
            "title": "파이썬 7일 계획",
            "course_name": "파이썬",
            "goal": "반복문 익히기",
            "current_level": 3,
            "start_date": today,
        }
        task = {
            "id": "task-1",
            "scheduled_date": today,
            "task_type": "learn",
            "title": "반복문 핵심 익히기",
            "description": "for문의 동작을 정리합니다.",
            "estimated_minutes": 30,
            "status": "pending",
            "source_type": "weekly_plan",
            "review_stage": None,
            "review_interval_days": None,
        }
        completed_task = {
            **task,
            "id": "task-2",
            "title": "반복문 문제 풀기",
            "status": "completed",
        }

        with (
            patch(
                "views.dashboard_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.dashboard_view.get_study_plan_tasks",
                return_value=[task, completed_task],
            ),
            patch(
                "views.dashboard_view.get_course_concept_masteries",
                return_value=[],
            ),
            patch(
                "views.dashboard_view.render_review_material_section"
            ) as material_section,
            patch(
                "views.dashboard_view.render_gamification_dashboard_summary"
            ) as gamification_summary,
        ):
            app = AppTest.from_function(
                render_dashboard_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("오늘 학습", [item.value for item in app.header])
        self.assertIn("오늘 할 일", [item.value for item in app.subheader])
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["이 계획의 오늘 과제", "남은 과제", "예상 학습시간"],
        )
        self.assertEqual(len(app.radio), 1)
        self.assertEqual(len(app.radio[0].options), 2)
        material_section.assert_called_once()
        gamification_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
