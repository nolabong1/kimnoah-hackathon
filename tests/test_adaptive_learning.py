import unittest
from copy import deepcopy
from uuid import UUID

from pydantic import ValidationError

from models.concept_mastery import (
    AdaptiveQuizAnalysis,
    AutoReviewTaskSummary,
)
from services.concept_mastery_repository import (
    get_course_concept_masteries,
    get_quiz_attempt_analysis,
)
from services.quiz_repository import submit_quiz_attempt
from services.study_plan_repository import reset_today_test_progress
from views.dashboard_view import _get_next_auto_review_tasks
from views.spaced_review_ui import get_spaced_review_label


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
QUIZ_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"
CONCEPT_A_ID = "55555555-5555-4555-8555-555555555555"
CONCEPT_B_ID = "66666666-6666-4666-8666-666666666666"
TASK_ID = "77777777-7777-4777-8777-777777777777"
SUBMISSION_KEY = "88888888-8888-4888-8888-888888888888"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableRequest:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.limit_count = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.rows = [
            row for row in self.rows
            if row.get(field) == value
        ]
        return self

    def in_(self, field, values):
        allowed_values = set(values)
        self.rows = [
            row for row in self.rows
            if row.get(field) in allowed_values
        ]
        return self

    def order(self, field, desc=False):
        self.rows.sort(
            key=lambda row: row.get(field) or "",
            reverse=desc,
        )
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        rows = self.rows
        if self.limit_count is not None:
            rows = rows[:self.limit_count]
        return FakeResponse(rows)


class FakeRpcRequest:
    def __init__(self, data):
        self.data = deepcopy(data)

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, table_rows=None, rpc_results=None):
        self.table_rows = table_rows or {}
        self.rpc_results = rpc_results or {}
        self.rpc_calls = []

    def table(self, name):
        return FakeTableRequest(self.table_rows.get(name, []))

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, deepcopy(params)))
        return FakeRpcRequest(self.rpc_results.get(name))


def mastery_summary(
    concept_id,
    concept_key,
    concept_name,
    mastery_score,
    incorrect_count,
    consecutive_incorrect_count,
    last_answer_correct,
):
    return {
        "concept_id": concept_id,
        "course_key": "python",
        "concept_key": concept_key,
        "concept_name": concept_name,
        "mastery_score": mastery_score,
        "correct_count": 1,
        "incorrect_count": incorrect_count,
        "consecutive_incorrect_count": consecutive_incorrect_count,
        "last_answer_correct": last_answer_correct,
        "last_assessed_at": "2026-08-16T02:00:00+00:00",
    }


class AdaptiveLearningModelTests(unittest.TestCase):
    def test_adaptive_analysis_uses_empty_collection_defaults(self):
        analysis = AdaptiveQuizAnalysis(attempt_id=ATTEMPT_ID)

        self.assertEqual(analysis.mastery_changes, [])
        self.assertEqual(analysis.concept_masteries, [])
        self.assertEqual(analysis.weak_concepts, [])
        self.assertEqual(analysis.auto_review_tasks, [])

    def test_review_stage_requires_matching_interval(self):
        with self.assertRaises(ValidationError):
            AutoReviewTaskSummary(
                task_id=TASK_ID,
                plan_id=PLAN_ID,
                concept_id=CONCEPT_A_ID,
                concept_name="반복문",
                title="반복문 간격 복습",
                scheduled_date="2026-08-17",
                estimated_minutes=20,
                review_stage=2,
                review_interval_days=1,
            )


class AdaptiveLearningRepositoryTests(unittest.TestCase):
    def test_course_masteries_are_sorted_weak_first(self):
        weak = mastery_summary(
            CONCEPT_A_ID,
            "loop",
            "반복문",
            45,
            2,
            2,
            False,
        )
        supabase = FakeSupabase(
            table_rows={
                "learning_concepts": [
                    {
                        "id": CONCEPT_A_ID,
                        "user_id": USER_ID,
                        "course_key": "python",
                        "concept_key": "loop",
                        "canonical_name": "반복문",
                    },
                    {
                        "id": CONCEPT_B_ID,
                        "user_id": USER_ID,
                        "course_key": "python",
                        "concept_key": "function",
                        "canonical_name": "함수",
                    },
                ],
                "concept_mastery": [
                    {
                        **{
                            key: value
                            for key, value in weak.items()
                            if key not in {
                                "course_key",
                                "concept_key",
                                "concept_name",
                            }
                        },
                        "user_id": USER_ID,
                    },
                    {
                        "concept_id": CONCEPT_B_ID,
                        "user_id": USER_ID,
                        "mastery_score": 75,
                        "correct_count": 3,
                        "incorrect_count": 0,
                        "consecutive_incorrect_count": 0,
                        "last_answer_correct": True,
                        "last_assessed_at": "2026-08-16T02:00:00+00:00",
                    },
                ],
            },
            rpc_results={"get_current_weak_concepts": [weak]},
        )

        result = get_course_concept_masteries(
            supabase,
            USER_ID,
            "python",
        )

        self.assertEqual(
            [row["concept_name"] for row in result],
            ["반복문", "함수"],
        )
        self.assertTrue(result[0]["is_weak"])
        self.assertFalse(result[1]["is_weak"])

    def test_saved_attempt_analysis_rebuilds_changes_and_review(self):
        weak = mastery_summary(
            CONCEPT_A_ID,
            "loop",
            "반복문",
            45,
            2,
            2,
            False,
        )
        supabase = FakeSupabase(
            table_rows={
                "concept_mastery_events": [
                    {
                        "user_id": USER_ID,
                        "quiz_attempt_id": ATTEMPT_ID,
                        "concept_id": CONCEPT_A_ID,
                        "question_index": 0,
                        "is_correct": False,
                        "score_before": 60,
                        "score_delta": -15,
                        "score_after": 45,
                    }
                ],
                "learning_concepts": [
                    {
                        "id": CONCEPT_A_ID,
                        "user_id": USER_ID,
                        "course_key": "python",
                        "concept_key": "loop",
                        "canonical_name": "반복문",
                    }
                ],
                "concept_mastery": [
                    {
                        "concept_id": CONCEPT_A_ID,
                        "user_id": USER_ID,
                        "mastery_score": 45,
                        "correct_count": 1,
                        "incorrect_count": 2,
                        "consecutive_incorrect_count": 2,
                        "last_answer_correct": False,
                        "last_assessed_at": "2026-08-16T02:00:00+00:00",
                    }
                ],
                "study_tasks": [
                    {
                        "id": TASK_ID,
                        "user_id": USER_ID,
                        "plan_id": PLAN_ID,
                        "concept_id": CONCEPT_A_ID,
                        "title": "반복문 약점 복습",
                        "scheduled_date": "2026-08-17",
                        "estimated_minutes": 20,
                        "status": "pending",
                        "source_type": "weakness_review",
                        "source_quiz_attempt_id": ATTEMPT_ID,
                        "review_stage": 1,
                        "review_interval_days": 1,
                        "created_at": "2026-08-16T02:00:00+00:00",
                    }
                ],
            },
            rpc_results={"get_current_weak_concepts": [weak]},
        )

        result = get_quiz_attempt_analysis(
            supabase,
            USER_ID,
            PLAN_ID,
            ATTEMPT_ID,
        )

        self.assertEqual(result["attempt_id"], ATTEMPT_ID)
        self.assertEqual(result["mastery_changes"][0]["score_delta"], -15)
        self.assertTrue(result["mastery_changes"][0]["is_weak"])
        self.assertEqual(result["concept_masteries"][0]["mastery_score"], 45)
        self.assertEqual(result["weak_concepts"][0]["concept_name"], "반복문")
        self.assertEqual(result["auto_review_tasks"][0]["task_id"], TASK_ID)
        self.assertEqual(
            result["auto_review_tasks"][0]["review_stage"],
            1,
        )
        self.assertEqual(
            result["auto_review_tasks"][0][
                "review_interval_days"
            ],
            1,
        )

    def test_submission_key_and_answers_are_forwarded_to_rpc(self):
        supabase = FakeSupabase(
            rpc_results={
                "submit_quiz_attempt": {
                    "attempt_id": ATTEMPT_ID,
                    "score": 100,
                    "mastery_changes": [],
                    "weak_concepts": [],
                    "auto_review_tasks": [],
                }
            }
        )

        result = submit_quiz_attempt(
            supabase,
            QUIZ_ID,
            "2026-08-16T02:00:00+00:00",
            [0, 1],
            SUBMISSION_KEY,
        )

        self.assertEqual(result["attempt_id"], ATTEMPT_ID)
        self.assertEqual(result["score"], 100)
        rpc_name, params = supabase.rpc_calls[0]
        self.assertEqual(rpc_name, "submit_quiz_attempt")
        self.assertEqual(params["p_answers"], [0, 1])
        self.assertEqual(
            params["p_submission_key"],
            str(UUID(SUBMISSION_KEY)),
        )

    def test_reset_requires_and_returns_mapping_response(self):
        expected = {
            "removed_quiz_attempt_count": 1,
            "removed_mastery_event_count": 2,
            "removed_auto_review_task_count": 1,
        }
        supabase = FakeSupabase(
            rpc_results={"reset_today_test_progress": expected}
        )

        result = reset_today_test_progress(supabase)

        self.assertEqual(result, expected)
        self.assertEqual(
            supabase.rpc_calls,
            [("reset_today_test_progress", {})],
        )

    def test_reset_rejects_invalid_response(self):
        supabase = FakeSupabase(
            rpc_results={"reset_today_test_progress": []}
        )

        with self.assertRaises(RuntimeError):
            reset_today_test_progress(supabase)


class AdaptiveLearningDashboardTests(unittest.TestCase):
    def test_spaced_review_label_describes_stage_and_interval(self):
        label = get_spaced_review_label(
            {
                "source_type": "weakness_review",
                "review_stage": 2,
                "review_interval_days": 3,
            }
        )

        self.assertEqual(
            label,
            "간격 반복 2/3 · 목표 간격 3일",
        )

    def test_regular_task_has_no_spaced_review_label(self):
        self.assertIsNone(
            get_spaced_review_label(
                {
                    "source_type": "weekly_plan",
                    "review_stage": None,
                    "review_interval_days": None,
                }
            )
        )

    def test_next_review_uses_nearest_pending_date(self):
        tasks = [
            {
                "id": "past",
                "source_type": "weakness_review",
                "status": "pending",
                "scheduled_date": "2026-08-15",
            },
            {
                "id": "completed",
                "source_type": "weakness_review",
                "status": "completed",
                "scheduled_date": "2026-08-16",
            },
            {
                "id": "regular",
                "source_type": "weekly_plan",
                "status": "pending",
                "scheduled_date": "2026-08-16",
            },
            {
                "id": "next-a",
                "source_type": "weakness_review",
                "status": "pending",
                "scheduled_date": "2026-08-17",
            },
            {
                "id": "next-b",
                "source_type": "weakness_review",
                "status": "pending",
                "scheduled_date": "2026-08-17",
            },
            {
                "id": "later",
                "source_type": "weakness_review",
                "status": "pending",
                "scheduled_date": "2026-08-18",
            },
        ]

        result = _get_next_auto_review_tasks(
            tasks,
            "2026-08-16",
        )

        self.assertEqual(
            [task["id"] for task in result],
            ["next-a", "next-b"],
        )


if __name__ == "__main__":
    unittest.main()
