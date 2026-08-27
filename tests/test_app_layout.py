import ast
import inspect
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch
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


def render_create_plan_test_page(supabase, user):
    from views.create_plan_view import render_create_plan

    render_create_plan(supabase, user)


def render_saved_plans_test_page(supabase, user):
    from views.saved_plans_view import render_saved_plans

    render_saved_plans(supabase, user)


def render_source_review_test_page(supabase, user):
    from views.source_review_material_view import (
        render_source_review_material,
    )

    render_source_review_material(supabase, user)


def render_tutor_test_page(supabase, user):
    from views.tutor_view import render_tutor

    render_tutor(supabase, user)


def render_mastery_test_page(supabase, user):
    from views.mastery_dashboard_view import render_mastery_dashboard

    render_mastery_dashboard(supabase, user)


def render_weekly_review_test_page(supabase, user):
    from views.weekly_review_view import render_weekly_review

    render_weekly_review(supabase, user)


def render_ui_components_test_page():
    from views.ui_components import (
        MetricItem,
        content_frame,
        render_empty_state,
        render_metric_row,
        render_page_header,
    )

    with content_frame(960):
        render_page_header(
            "테스트 대시보드",
            "공통 UI 컴포넌트를 확인합니다.",
        )
        render_metric_row(
            [
                MetricItem(
                    "남은 과제",
                    "2개",
                    icon=":material/pending_actions:",
                ),
                MetricItem(
                    "예상 학습시간",
                    "40분",
                    icon=":material/schedule:",
                ),
            ]
        )
        render_empty_state(
            "표시할 항목이 없습니다",
            "다른 조건을 선택해주세요.",
        )


class AppLayoutTests(unittest.TestCase):
    def test_desktop_layout_uses_wide_expanded_sidebar(self):
        page_config = _get_streamlit_call_keywords("set_page_config")

        self.assertEqual(page_config["layout"], "wide")
        self.assertEqual(page_config["initial_sidebar_state"], "expanded")

    def test_navigation_uses_expanded_sidebar(self):
        navigation = _get_streamlit_call_keywords("navigation")

        self.assertEqual(navigation["position"], "sidebar")
        self.assertTrue(navigation["expanded"])

    def test_customization_features_are_direct_navigation_pages(self):
        app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        gamification_source = (
            PROJECT_ROOT / "views" / "gamification_view.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"꾸미기": [', app_source)
        for page_name in (
            "shop_page",
            "inventory_page",
            "study_room_page",
            "collection_page",
        ):
            self.assertIn(page_name, app_source)
        for old_nested_tab in (
            '"상점",',
            '"내 아이템",',
            '"학습방",',
            '"컬렉션",',
        ):
            self.assertNotIn(old_nested_tab, gamification_source)

    def test_approved_theme_tokens_are_configured(self):
        import tomllib

        with (PROJECT_ROOT / ".streamlit" / "config.toml").open(
            "rb"
        ) as config_file:
            theme = tomllib.load(config_file)["theme"]

        self.assertEqual(theme["base"], "light")
        self.assertEqual(theme["primaryColor"], "#5B4FE5")
        self.assertEqual(theme["backgroundColor"], "#F7F8FC")
        self.assertEqual(theme["textColor"], "#171923")
        self.assertEqual(theme["baseRadius"], "12px")

    def test_shared_ui_components_render_without_custom_css(self):
        app = AppTest.from_function(
            render_ui_components_test_page
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertIn(
            "테스트 대시보드",
            [item.value for item in app.title],
        )
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["남은 과제", "예상 학습시간"],
        )
        self.assertNotIn("unsafe_allow_html", (
            PROJECT_ROOT / "views" / "ui_components.py"
        ).read_text(encoding="utf-8"))

    def test_remaining_pages_use_approved_content_frames(self):
        app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("with content_frame(AUTH_CONTENT_WIDTH):", app_source)
        self.assertGreaterEqual(
            app_source.count("with content_frame(STANDARD_CONTENT_WIDTH):"),
            4,
        )
        self.assertGreaterEqual(
            app_source.count("with content_frame(DASHBOARD_CONTENT_WIDTH):"),
            3,
        )

    def test_ai_tool_setup_pages_use_compact_two_column_layouts(self):
        plan = {
            "id": PLAN_ID,
            "title": "파이썬 7일 계획",
            "course_name": "파이썬",
            "goal": "반복문 익히기",
            "current_level": 3,
        }
        user = SimpleNamespace(id=USER_ID)

        with patch(
            "views.source_review_material_view.get_user_study_plans",
            return_value=[plan],
        ):
            source_app = AppTest.from_function(
                render_source_review_test_page,
                args=(object(), user),
            ).run()

        self.assertEqual(list(source_app.exception), [])
        self.assertIn(
            "AI 복습 자료 만들기",
            [item.value for item in source_app.title],
        )
        self.assertIn(
            "원본 준비",
            [item.value for item in source_app.subheader],
        )

        with (
            patch(
                "views.tutor_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.tutor_view.get_study_plan_tasks",
                return_value=[],
            ),
            patch(
                "views.tutor_view.get_learning_materials_by_plan",
                return_value=[],
            ),
            patch(
                "views.tutor_view.get_review_materials_by_plan",
                return_value=[],
            ),
        ):
            tutor_app = AppTest.from_function(
                render_tutor_test_page,
                args=(object(), user),
            ).run()

        self.assertEqual(list(tutor_app.exception), [])
        self.assertIn(
            "단계별 힌트 AI 튜터",
            [item.value for item in tutor_app.title],
        )
        self.assertIn(
            "연결 정보",
            [item.value for item in tutor_app.subheader],
        )
        self.assertIn(
            "질문과 현재 풀이",
            [item.value for item in tutor_app.subheader],
        )

    def test_mastery_page_separates_overview_and_concept_detail(self):
        mastery = {
            "course_key": "python",
            "course_name": "파이썬",
            "concept_name": "반복문",
            "mastery_score": 45,
            "correct_count": 1,
            "incorrect_count": 2,
            "consecutive_incorrect_count": 2,
            "last_assessed_at": "2026-08-17T08:00:00+00:00",
            "is_weak": True,
        }
        with patch(
            "views.mastery_dashboard_view.get_user_concept_masteries",
            return_value=[mastery],
        ):
            app = AppTest.from_function(
                render_mastery_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            [tab.label for tab in app.tabs],
            ["과목 비교", "개념 상세"],
        )
        self.assertEqual(
            [metric.label for metric in app.metric[:4]],
            ["평가된 과목", "평가된 개념", "전체 개념 평균", "현재 취약 개념"],
        )

    def test_weekly_review_separates_record_review_and_next_plan(self):
        from models.weekly_review import WeeklyStatisticsSnapshot

        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        plan = {
            "id": PLAN_ID,
            "title": "파이썬 7일 계획",
            "course_name": "파이썬",
            "goal": "반복문 익히기",
            "current_level": 3,
            "start_date": today.isoformat(),
            "target_date": today.isoformat(),
        }
        statistics = WeeklyStatisticsSnapshot(
            plan_title=plan["title"],
            course_name=plan["course_name"],
            plan_start_date=today,
            plan_target_date=today,
            total_tasks=1,
            completed_tasks=1,
            pending_tasks=0,
            skipped_tasks=0,
            completion_rate=100,
            total_planned_minutes=30,
            completed_estimated_minutes=30,
            scheduled_study_days=1,
            days_with_completed_task=1,
            completed_by_task_type={"learn": 1, "review": 0, "quiz": 0},
            completed_estimated_minutes_by_date={today.isoformat(): 30},
            task_completion_counts_by_date={today.isoformat(): 1},
        )
        with (
            patch(
                "views.weekly_review_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.weekly_review_view.get_study_tasks_by_plan_ids",
                return_value={PLAN_ID: [{"status": "completed"}]},
            ) as get_tasks_by_plan_ids,
            patch(
                "views.weekly_review_view.is_weekly_review_eligible",
                return_value=True,
            ),
            patch(
                "views.weekly_review_view.get_weekly_review_by_plan",
                return_value=None,
            ),
            patch(
                "views.weekly_review_view.calculate_weekly_statistics",
                return_value=statistics,
            ),
        ):
            app = AppTest.from_function(
                render_weekly_review_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        get_tasks_by_plan_ids.assert_called_once_with(
            supabase=ANY,
            user_id=USER_ID,
            plan_ids=[PLAN_ID],
        )
        self.assertEqual(
            [tab.label for tab in app.tabs],
            ["학습 기록과 나의 회고", "AI 주간 회고", "다음 주 계획"],
        )

    def test_tutor_final_answer_uses_explicit_confirmation_dialog(self):
        from models.tutor import TutorGuidance
        from views.tutor_state import create_tutor_session_state

        guidance = TutorGuidance.model_validate(
            {
                "problem_summary": "두 수를 더하는 문제입니다.",
                "required_concepts": ["덧셈"],
                "hints": [
                    {
                        "level": level,
                        "title": f"힌트 {level}",
                        "content": f"단계 {level}을 생각하세요.",
                        "guiding_question": "다음 단계는 무엇인가요?",
                    }
                    for level in (1, 2, 3)
                ],
                "final_solution": {
                    "final_answer": "2",
                    "reasoning_steps": ["1과 1을 더합니다."],
                    "why_solution_works": "덧셈 정의를 적용합니다.",
                    "common_mistakes": ["수를 빠뜨리지 않습니다."],
                    "self_check_question": "2+1도 계산해보세요.",
                },
            }
        )
        app = AppTest.from_function(
            render_tutor_test_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )
        for key, value in create_tutor_session_state(
            session_id="session-1",
            user_id=USER_ID,
            plan_id=PLAN_ID,
            task_id=None,
            material_key=None,
            course_name="수학",
            task_title=None,
            reference_title=None,
            reference_context=None,
            reference_was_limited=False,
            question="1+1은?",
            original_attempt="",
            guidance=guidance,
        ).items():
            app.session_state[key] = value

        app.run()
        self.assertEqual(list(app.exception), [])
        show_answer = next(
            button
            for button in app.button
            if button.label == "정답 보기"
        )
        app = show_answer.click().run()

        self.assertEqual(list(app.exception), [])
        self.assertIn(
            "정답 확인하기",
            [button.label for button in app.button],
        )
        self.assertIn(
            "계속 풀어보기",
            [button.label for button in app.button],
        )
        self.assertNotIn(
            "최종 정답과 전체 풀이",
            [item.value for item in app.markdown],
        )

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
                "views.dashboard_view.get_dashboard_snapshot",
                return_value={
                    "plan_tasks": [task, completed_task],
                    "concept_masteries": [],
                    "achievements": [],
                    "challenges": [],
                    "badge_showcase": [],
                },
            ),
            patch(
                "views.dashboard_view.render_review_material_section"
            ) as material_section,
            patch(
                "views.dashboard_view."
                "render_gamification_dashboard_summary_from_data"
            ) as gamification_summary,
        ):
            app = AppTest.from_function(
                render_dashboard_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("오늘 학습", [item.value for item in app.title])
        self.assertIn("오늘 할 일", [item.value for item in app.subheader])
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["이 계획의 오늘 과제", "남은 과제", "예상 학습시간"],
        )
        self.assertEqual(len(app.radio), 1)
        self.assertEqual(len(app.radio[0].options), 2)
        material_section.assert_called_once()
        gamification_summary.assert_called_once()

    def test_create_plan_separates_inputs_preview_and_save(self):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        task = SimpleNamespace(
            task_type="learn",
            title="반복문 개념 익히기",
            description="for문의 실행 순서를 정리합니다.",
            estimated_minutes=30,
        )
        day = SimpleNamespace(
            day_offset=0,
            daily_focus="반복문 기초",
            tasks=[task],
        )
        plan = SimpleNamespace(
            title="파이썬 7일 계획",
            level_assessment="기본 문법을 복습하면 좋습니다.",
            weekly_goal="반복문을 활용한 프로그램 완성",
            strategy="개념 학습 후 짧은 문제를 풉니다.",
            days=[day],
            motivation_message="작은 과제를 꾸준히 완료해보세요.",
        )
        app = AppTest.from_function(
            render_create_plan_test_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )
        app.session_state["generated_plan"] = plan
        app.session_state["generated_plan_start_date"] = today
        app.session_state["generated_plan_metadata"] = {
            "course_name": "파이썬",
            "goal": "반복문 익히기",
            "current_level": 3,
            "start_date": today,
            "available_schedule": {
                f"{day_offset}일차": 60
                for day_offset in range(7)
            },
        }
        app.session_state["generated_plan_saved"] = False

        with (
            patch(
                "views.create_plan_view.generate_weekly_study_plan"
            ) as generate_plan,
            patch(
                "views.create_plan_view.save_weekly_study_plan"
            ) as save_plan,
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("계획 만들기", [item.value for item in app.title])
        self.assertEqual(len(app.number_input), 7)
        self.assertIn(
            "1. 계획 조건",
            [item.value for item in app.subheader],
        )
        self.assertIn(
            "3. AI 학습계획 미리보기",
            [item.value for item in app.subheader],
        )
        self.assertIn(
            "4. 계획 저장",
            [item.value for item in app.subheader],
        )
        self.assertIn(
            "AI 학습계획 만들기",
            [button.label for button in app.button],
        )
        self.assertIn(
            "이 계획 저장하기",
            [button.label for button in app.button],
        )
        generate_plan.assert_not_called()
        save_plan.assert_not_called()

    def test_saved_plans_renders_only_selected_date_details(self):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        today_text = today.isoformat()
        tomorrow_text = (today + timedelta(days=1)).isoformat()
        plan = {
            "id": PLAN_ID,
            "title": "파이썬 7일 계획",
            "course_name": "파이썬",
            "goal": "반복문 익히기",
            "current_level": 3,
            "start_date": today_text,
            "target_date": tomorrow_text,
        }
        learn_task = {
            "id": "task-today",
            "scheduled_date": today_text,
            "task_type": "learn",
            "title": "반복문 핵심 익히기",
            "description": "for문의 동작을 정리합니다.",
            "estimated_minutes": 30,
            "status": "pending",
            "source_type": "weekly_plan",
            "review_stage": None,
            "review_interval_days": None,
        }
        quiz_task = {
            **learn_task,
            "id": "task-tomorrow",
            "scheduled_date": tomorrow_text,
            "task_type": "quiz",
            "title": "반복문 퀴즈",
        }

        with (
            patch(
                "views.saved_plans_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.saved_plans_view.get_study_plan_tasks",
                return_value=[learn_task, quiz_task],
            ),
            patch(
                "views.saved_plans_view.render_review_material_section"
            ) as material_section,
            patch(
                "views.saved_plans_view.render_quiz_section",
                return_value=False,
            ) as quiz_section,
        ):
            app = AppTest.from_function(
                render_saved_plans_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("저장된 계획", [item.value for item in app.title])
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["과목", "시작일", "종료일"],
        )
        date_select = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "상세 내용을 확인할 날짜"
        )
        self.assertEqual(
            list(date_select.options),
            [
                f"{today_text} · 0/1 완료 · 30분",
                f"{tomorrow_text} · 0/1 완료 · 30분",
            ],
        )
        self.assertEqual(date_select.value, today_text)
        self.assertEqual(len(app.expander), 0)
        material_section.assert_called_once()
        quiz_section.assert_not_called()

        app.session_state["saved_plan_pending_open_date"] = tomorrow_text
        with (
            patch(
                "views.saved_plans_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.saved_plans_view.get_study_plan_tasks",
                return_value=[learn_task, quiz_task],
            ),
            patch(
                "views.saved_plans_view.render_review_material_section"
            ) as future_material_section,
            patch(
                "views.saved_plans_view.render_quiz_section",
                return_value=False,
            ) as future_quiz_section,
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        date_select = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "상세 내용을 확인할 날짜"
        )
        self.assertEqual(date_select.value, tomorrow_text)
        future_material_section.assert_not_called()
        future_quiz_section.assert_called_once()

    def test_saved_plans_empty_state_links_to_create_plan(self):
        from views.saved_plans_view import PENDING_NAVIGATION_KEY

        with (
            patch(
                "views.saved_plans_view.get_user_study_plans",
                return_value=[],
            ),
            patch(
                "views.saved_plans_view.get_study_plan_tasks"
            ) as load_tasks,
        ):
            app = AppTest.from_function(
                render_saved_plans_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

            self.assertEqual(list(app.exception), [])
            self.assertTrue(
                any(
                    "저장된 학습계획이 없습니다" in item.value
                    for item in app.markdown
                )
            )
            create_button = next(
                button
                for button in app.button
                if button.label == "새 계획 만들기"
            )
            create_button.click().run()

        self.assertEqual(
            app.session_state[PENDING_NAVIGATION_KEY],
            "계획 만들기",
        )
        load_tasks.assert_not_called()

    def test_saved_plans_load_failure_does_not_show_empty_state(self):
        with (
            patch(
                "views.saved_plans_view.get_user_study_plans",
                side_effect=RuntimeError("database detail"),
            ),
            patch(
                "views.saved_plans_view.get_study_plan_tasks"
            ) as load_tasks,
            patch(
                "views.saved_plans_view.render_empty_state"
            ) as empty_state,
            patch(
                "views.error_feedback.report_exception",
                return_value="A1B2C3D4",
            ),
        ):
            app = AppTest.from_function(
                render_saved_plans_test_page,
                args=(object(), SimpleNamespace(id=USER_ID)),
            ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.error), 1)
        self.assertNotIn("database detail", app.error[0].value)
        self.assertIn("A1B2C3D4", app.error[0].value)
        empty_state.assert_not_called()
        load_tasks.assert_not_called()

    def test_saved_plan_tasks_use_consistent_full_page_width(self):
        from views import saved_plans_view

        source = inspect.getsource(saved_plans_view.render_saved_plans)

        self.assertNotIn("selected_date_has_quiz", source)
        self.assertNotIn("date_detail_column", source)
        schedule_container = source.index(
            'st.subheader("학습 일정")'
        )
        task_list = source.rindex("for task in selected_tasks:")
        self.assertGreater(task_list, schedule_container)


if __name__ == "__main__":
    unittest.main()
