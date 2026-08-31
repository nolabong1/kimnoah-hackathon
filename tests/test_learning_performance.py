import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from streamlit.testing.v1 import AppTest

from models.learning_objective import StoredLearningObjective
from services.learning_performance_repository import (
    get_learning_performance_data,
)
from services.learning_performance_service import (
    build_learning_performance_html,
    build_learning_performance_report,
    build_performance_highlights,
    summarize_before_after_evidence,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
OBJECTIVE_A_ID = "33333333-3333-4333-8333-333333333331"
OBJECTIVE_B_ID = "33333333-3333-4333-8333-333333333332"
QUIZ_A_ID = "44444444-4444-4444-8444-444444444441"
QUIZ_B_ID = "44444444-4444-4444-8444-444444444442"
ATTEMPT_A1_ID = "55555555-5555-4555-8555-555555555551"
ATTEMPT_A2_ID = "55555555-5555-4555-8555-555555555552"
ATTEMPT_B1_ID = "55555555-5555-4555-8555-555555555553"
CONCEPT_A_ID = "66666666-6666-4666-8666-666666666661"
CONCEPT_B_ID = "66666666-6666-4666-8666-666666666662"


def _performance_data() -> dict:
    return {
        "plan": {
            "id": PLAN_ID,
            "title": "파이썬 조건문 7일 계획",
            "course_name": "파이썬",
            "start_date": "2026-08-01",
            "target_date": "2026-08-07",
        },
        "tasks": [
            {
                "id": "task-1",
                "learning_objective_id": OBJECTIVE_A_ID,
                "task_type": "learn",
                "estimated_minutes": 30,
                "status": "completed",
            },
            {
                "id": "task-2",
                "learning_objective_id": OBJECTIVE_A_ID,
                "task_type": "quiz",
                "estimated_minutes": 15,
                "status": "completed",
            },
            {
                "id": "task-3",
                "learning_objective_id": OBJECTIVE_B_ID,
                "task_type": "review",
                "estimated_minutes": 20,
                "status": "pending",
            },
        ],
        "objectives": [
            {"id": OBJECTIVE_A_ID, "title": "조건식 설명", "sort_order": 0},
            {"id": OBJECTIVE_B_ID, "title": "조건식 적용", "sort_order": 1},
        ],
        "quizzes": [
            {
                "id": QUIZ_A_ID,
                "title": "조건식 기초 퀴즈",
                "learning_objective_id": OBJECTIVE_A_ID,
            },
            {
                "id": QUIZ_B_ID,
                "title": "조건식 적용 퀴즈",
                "learning_objective_id": OBJECTIVE_B_ID,
            },
        ],
        "attempts": [
            {
                "id": ATTEMPT_A1_ID,
                "quiz_id": QUIZ_A_ID,
                "attempt_number": 1,
                "score": 40,
                "submitted_at": "2026-08-02T01:00:00+00:00",
            },
            {
                "id": ATTEMPT_A2_ID,
                "quiz_id": QUIZ_A_ID,
                "attempt_number": 2,
                "score": 80,
                "submitted_at": "2026-08-03T01:00:00+00:00",
            },
            {
                "id": ATTEMPT_B1_ID,
                "quiz_id": QUIZ_B_ID,
                "attempt_number": 1,
                "score": 60,
                "submitted_at": "2026-08-04T01:00:00+00:00",
            },
        ],
        "mastery_events": [
            {
                "concept_id": CONCEPT_A_ID,
                "quiz_attempt_id": ATTEMPT_A1_ID,
                "question_index": 0,
                "is_correct": False,
                "score_before": 50,
                "score_delta": -15,
                "score_after": 35,
            },
            {
                "concept_id": CONCEPT_A_ID,
                "quiz_attempt_id": ATTEMPT_A2_ID,
                "question_index": 0,
                "is_correct": True,
                "score_before": 35,
                "score_delta": 10,
                "score_after": 45,
            },
            {
                "concept_id": CONCEPT_B_ID,
                "quiz_attempt_id": ATTEMPT_B1_ID,
                "question_index": 1,
                "is_correct": True,
                "score_before": 50,
                "score_delta": 10,
                "score_after": 60,
            },
        ],
        "concepts": [
            {"id": CONCEPT_A_ID, "canonical_name": "조건식"},
            {"id": CONCEPT_B_ID, "canonical_name": "분기 적용"},
        ],
        "current_masteries": [
            {
                "concept_id": CONCEPT_A_ID,
                "mastery_score": 45,
                "consecutive_incorrect_count": 1,
            },
            {
                "concept_id": CONCEPT_B_ID,
                "mastery_score": 60,
                "consecutive_incorrect_count": 0,
            },
        ],
    }


class LearningPerformanceServiceTests(unittest.TestCase):
    def test_report_aggregates_tasks_quizzes_mastery_and_objectives(self):
        report = build_learning_performance_report(_performance_data())

        self.assertEqual(report.completed_tasks, 2)
        self.assertEqual(report.completion_rate, 66.7)
        self.assertEqual(report.completed_estimated_minutes, 45)
        self.assertEqual(report.average_first_score, 50.0)
        self.assertEqual(report.average_latest_score, 70.0)
        self.assertEqual(report.average_score_change, 20.0)
        self.assertEqual(report.total_quiz_attempts, 3)
        self.assertEqual(report.plan_mastery_score_delta, 5)
        self.assertEqual(report.improved_concept_count, 1)
        self.assertTrue(report.concepts[1].current_is_weak)
        self.assertEqual(report.objectives[0].completion_rate, 100.0)
        self.assertEqual(report.objectives[0].latest_quiz_average, 80.0)

    def test_zero_activity_is_safe_and_does_not_invent_improvement(self):
        data = _performance_data()
        data.update(
            {
                "tasks": [],
                "objectives": [],
                "quizzes": [],
                "attempts": [],
                "mastery_events": [],
                "concepts": [],
                "current_masteries": [],
            }
        )

        report = build_learning_performance_report(data)
        highlights = build_performance_highlights(report)

        self.assertEqual(report.completion_rate, 0.0)
        self.assertIsNone(report.average_latest_score)
        self.assertEqual(report.plan_mastery_score_delta, 0)
        self.assertIn("응시 기록이 없습니다", highlights[1])
        self.assertIn("아직 없습니다", highlights[2])

    def test_quiz_history_is_ordered_by_attempt_number(self):
        data = _performance_data()
        data["attempts"] = list(reversed(data["attempts"]))

        report = build_learning_performance_report(data)

        self.assertEqual(report.quizzes[0].score_history, [40, 80])
        self.assertEqual(report.quizzes[0].score_change, 40)

    def test_stored_objective_uuid_is_normalized_for_report_links(self):
        data = _performance_data()
        data["objectives"] = [
            StoredLearningObjective(
                id=OBJECTIVE_A_ID,
                user_id=USER_ID,
                plan_id=PLAN_ID,
                objective_key="explain_condition",
                title="조건식 설명",
                description="조건식의 평가 결과를 설명합니다.",
                target_depth="foundation",
                evidence_requirements=[
                    {"key": "explain", "description": "개념을 설명합니다."},
                    {"key": "apply", "description": "예제에 적용합니다."},
                    {
                        "key": "differentiate",
                        "description": "비슷한 개념을 구분합니다.",
                    },
                ],
                contract_hash="a" * 64,
                sort_order=1,
                origin="generated",
            )
        ]

        report = build_learning_performance_report(data)

        self.assertEqual(
            report.objectives[0].learning_objective_id,
            OBJECTIVE_A_ID,
        )
        self.assertEqual(report.objectives[0].task_count, 2)

    def test_before_after_summary_counts_only_direct_score_changes(self):
        report = build_learning_performance_report(_performance_data())

        summary = summarize_before_after_evidence(report)

        self.assertEqual(summary["evaluated_concept_count"], 2)
        self.assertEqual(summary["improved_concept_count"], 1)
        self.assertEqual(summary["score_threshold_reached_count"], 1)

    def test_html_report_contains_objective_and_student_evidence(self):
        report = build_learning_performance_report(_performance_data())

        html = build_learning_performance_html(
            report,
            reflection_answers={
                "went_well": "조건식 예제를 끝까지 풀었다.",
                "difficulty": "중첩 조건문이 어려웠다.",
            },
            ai_review_markdown="### AI 분석\n조건식 연습이 확인됐습니다.",
        )

        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', html)
        self.assertIn("완료 과제 기준 예상 학습량", html)
        self.assertIn("45분", html)
        self.assertIn("학습목표별 근거", html)
        self.assertIn("조건식 설명", html)
        self.assertIn("첫 평가 직전", html)
        self.assertIn("조건식 예제를 끝까지 풀었다.", html)
        self.assertIn("AI 주간 회고 분석", html)
        self.assertIn("인과관계를 단정하지 않습니다", html)
        self.assertIn("@media print", html)

    def test_html_report_handles_empty_assessment_and_review(self):
        data = _performance_data()
        data.update(
            {
                "objectives": [],
                "quizzes": [],
                "attempts": [],
                "mastery_events": [],
                "concepts": [],
                "current_masteries": [],
            }
        )
        report = build_learning_performance_report(data)

        html = build_learning_performance_html(report)

        self.assertIn("퀴즈 응시 기록이 없습니다", html)
        self.assertIn("개념 숙련도 평가 기록이 없습니다", html)
        self.assertIn("저장된 직접 회고 답변이 없습니다", html)

    def test_html_report_escapes_user_and_ai_content(self):
        report = build_learning_performance_report(_performance_data()).model_copy(
            update={"plan_title": "<script>alert('plan')</script>"}
        )

        html = build_learning_performance_html(
            report,
            reflection_answers={"went_well": '<img src=x onerror="alert(1)">'},
            ai_review_markdown="## 분석\n<script>alert('ai')</script>",
        )

        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert", html)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", html)


class _Query:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name

    def __getattr__(self, name):
        if name in {"select", "eq", "in_", "order", "limit"}:
            return lambda *args, **kwargs: self
        raise AttributeError(name)

    def execute(self):
        self.supabase.executed_tables.append(self.table_name)
        return SimpleNamespace(data=self.supabase.rows.get(self.table_name, []))


class _Supabase:
    def __init__(self, rows):
        self.rows = rows
        self.executed_tables = []

    def table(self, table_name):
        return _Query(self, table_name)


class LearningPerformanceRepositoryTests(unittest.TestCase):
    @patch(
        "services.learning_performance_repository."
        "get_learning_objectives_by_plan_ids",
        return_value={PLAN_ID: []},
    )
    def test_empty_quiz_plan_skips_attempt_and_mastery_queries(self, _objectives):
        supabase = _Supabase(
            {
                "study_plans": [
                    {
                        "id": PLAN_ID,
                        "user_id": USER_ID,
                        "title": "계획",
                    }
                ],
                "study_tasks": [],
                "quizzes": [],
            }
        )

        result = get_learning_performance_data(supabase, USER_ID, PLAN_ID)

        self.assertEqual(result["attempts"], [])
        self.assertEqual(
            supabase.executed_tables,
            ["study_plans", "study_tasks", "quizzes"],
        )

    @patch(
        "services.learning_performance_repository."
        "get_learning_objectives_by_plan_ids",
    )
    def test_wrong_plan_owner_is_rejected_before_other_queries(self, objectives):
        supabase = _Supabase(
            {
                "study_plans": [
                    {
                        "id": PLAN_ID,
                        "user_id": "99999999-9999-4999-8999-999999999999",
                    }
                ]
            }
        )

        with self.assertRaises(RuntimeError):
            get_learning_performance_data(supabase, USER_ID, PLAN_ID)

        objectives.assert_not_called()
        self.assertEqual(supabase.executed_tables, ["study_plans"])


def _render_performance_test_page(supabase, user):
    from views.learning_performance_view import render_learning_performance

    render_learning_performance(supabase, user)


class LearningPerformanceViewTests(unittest.TestCase):
    def test_report_view_renders_saved_plan_without_writes(self):
        data = _performance_data()
        plan = {
            **data["plan"],
            "current_level": 3,
            "goal": "조건문 이해",
            "available_schedule": {},
            "weekly_overview": [],
            "status": "active",
            "created_at": "2026-08-01T00:00:00+00:00",
        }
        app = AppTest.from_function(
            _render_performance_test_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )

        with (
            patch(
                "views.learning_performance_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.learning_performance_view.get_learning_performance_data",
                return_value=data,
            ) as load_performance,
            patch(
                "views.learning_performance_view.get_weekly_review_by_plan",
                return_value=None,
            ) as load_review,
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("학습 성과 리포트", [item.value for item in app.title])
        self.assertIn("성과 요약", [tab.label for tab in app.tabs])
        load_performance.assert_called_once_with(
            supabase=ANY,
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )
        load_review.assert_called_once()

    def test_report_view_separates_student_reflection_from_ai_review(self):
        data = _performance_data()
        plan = {
            **data["plan"],
            "current_level": 3,
            "goal": "조건문 이해",
            "available_schedule": {},
            "weekly_overview": [],
            "status": "active",
            "created_at": "2026-08-01T00:00:00+00:00",
        }
        review = {
            "week_start": "2026-08-01",
            "week_end": "2026-08-07",
            "reflection_answers": {
                "went_well": "조건식 예제를 끝까지 풀었다.",
                "difficulty": "중첩 조건문이 어려웠다.",
            },
            "ai_review_markdown": "### AI 분석\n조건식 연습이 확인됐습니다.",
        }
        app = AppTest.from_function(
            _render_performance_test_page,
            args=(object(), SimpleNamespace(id=USER_ID)),
        )

        with (
            patch(
                "views.learning_performance_view.get_user_study_plans",
                return_value=[plan],
            ),
            patch(
                "views.learning_performance_view.get_learning_performance_data",
                return_value=data,
            ),
            patch(
                "views.learning_performance_view.get_weekly_review_by_plan",
                return_value=review,
            ),
        ):
            app.run()

        self.assertEqual(list(app.exception), [])
        rendered_text = "\n".join(item.value for item in app.markdown)
        self.assertIn("학생이 직접 작성한 회고", rendered_text)
        self.assertIn("조건식 예제를 끝까지 풀었다.", rendered_text)
        self.assertIn("AI 회고 분석", rendered_text)
        self.assertEqual(len(app.download_button), 1)
        self.assertEqual(
            app.download_button[0].label,
            "읽기 쉬운 HTML 리포트 내려받기",
        )


if __name__ == "__main__":
    unittest.main()
