import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from services.quiz_repository import (
    RECENT_QUIZ_ATTEMPT_LIMIT,
    get_quiz_attempts,
    has_perfect_current_quiz_attempt,
)
from services.study_plan_repository import get_study_tasks_by_plan_ids
from views.quiz_ui import render_quiz_section


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_A_ID = "22222222-2222-4222-8222-222222222222"
PLAN_B_ID = "33333333-3333-4333-8333-333333333333"
QUIZ_ID = "44444444-4444-4444-8444-444444444444"
QUIZ_UPDATED_AT = "2026-08-26T00:00:00+00:00"


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeTableRequest:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.selected_fields = None
        self.filters = []
        self.in_filters = []
        self.orders = []
        self.limit_count = None

    def select(self, fields, **_kwargs):
        self.selected_fields = fields
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        self.rows = [
            row for row in self.rows if row.get(field) == value
        ]
        return self

    def in_(self, field, values):
        normalized_values = list(values)
        self.in_filters.append((field, normalized_values))
        allowed_values = set(normalized_values)
        self.rows = [
            row for row in self.rows if row.get(field) in allowed_values
        ]
        return self

    def order(self, field, desc=False):
        self.orders.append((field, desc))
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
            rows = rows[: self.limit_count]
        return FakeResponse(rows)


class FakeSupabase:
    def __init__(self, table_rows):
        self.table_rows = deepcopy(table_rows)
        self.table_calls = []
        self.requests = []

    def table(self, table_name):
        self.table_calls.append(table_name)
        request = FakeTableRequest(self.table_rows.get(table_name, []))
        self.requests.append(request)
        return request


class QuizAttemptQueryTests(unittest.TestCase):
    def test_recent_attempt_query_limits_large_history(self):
        attempts = [
            {
                "id": f"attempt-{attempt_number}",
                "user_id": USER_ID,
                "quiz_id": QUIZ_ID,
                "attempt_number": attempt_number,
            }
            for attempt_number in range(1, 26)
        ]
        supabase = FakeSupabase({"quiz_attempts": attempts})

        result = get_quiz_attempts(
            supabase=supabase,
            user_id=USER_ID,
            quiz_id=QUIZ_ID,
        )

        self.assertEqual(len(result), RECENT_QUIZ_ATTEMPT_LIMIT)
        self.assertEqual(result[0]["attempt_number"], 25)
        self.assertEqual(
            supabase.requests[0].limit_count,
            RECENT_QUIZ_ATTEMPT_LIMIT,
        )

    def test_completion_query_does_not_load_answers_or_snapshots(self):
        supabase = FakeSupabase(
            {
                "quiz_attempts": [
                    {
                        "id": "attempt-perfect",
                        "user_id": USER_ID,
                        "quiz_id": QUIZ_ID,
                        "quiz_updated_at": QUIZ_UPDATED_AT,
                        "correct_count": 5,
                        "total_questions": 5,
                        "answers": [0, 1, 2, 3, 0],
                        "questions_snapshot": [{"question": "무거운 데이터"}],
                    }
                ]
            }
        )

        result = has_perfect_current_quiz_attempt(
            supabase=supabase,
            user_id=USER_ID,
            quiz_id=QUIZ_ID,
            quiz_updated_at=QUIZ_UPDATED_AT,
            question_count=5,
        )

        self.assertTrue(result)
        request = supabase.requests[0]
        self.assertEqual(request.selected_fields, "id")
        self.assertEqual(request.limit_count, 1)
        self.assertNotIn("answers", request.selected_fields)
        self.assertNotIn("questions_snapshot", request.selected_fields)

    @patch("views.quiz_ui.get_quiz_attempts")
    @patch("views.quiz_ui.has_perfect_current_quiz_attempt", return_value=True)
    @patch("views.quiz_ui.get_quiz_by_task")
    @patch("views.quiz_ui.st")
    def test_closed_quiz_does_not_load_detailed_attempts(
        self,
        mock_streamlit,
        mock_get_quiz,
        _mock_completion_status,
        mock_get_attempts,
    ):
        mock_get_quiz.return_value = {
            "id": QUIZ_ID,
            "updated_at": QUIZ_UPDATED_AT,
            "question_count": 5,
        }
        mock_streamlit.toggle.return_value = False
        mock_streamlit.empty.return_value = MagicMock()

        completion_unlocked = render_quiz_section(
            supabase=object(),
            user_id=USER_ID,
            plan_id=PLAN_A_ID,
            course_name="파이썬",
            goal="반복문 익히기",
            current_level=3,
            task={"id": "task-1", "status": "pending"},
            widget_scope="performance_test",
        )

        self.assertTrue(completion_unlocked)
        mock_get_attempts.assert_not_called()


class WeeklyReviewBulkQueryTests(unittest.TestCase):
    def test_tasks_for_multiple_plans_use_one_table_query(self):
        supabase = FakeSupabase(
            {
                "study_tasks": [
                    {
                        "id": "task-b",
                        "user_id": USER_ID,
                        "plan_id": PLAN_B_ID,
                        "scheduled_date": "2026-08-27",
                        "created_at": "2026-08-20T00:00:02+00:00",
                    },
                    {
                        "id": "task-a",
                        "user_id": USER_ID,
                        "plan_id": PLAN_A_ID,
                        "scheduled_date": "2026-08-26",
                        "created_at": "2026-08-20T00:00:01+00:00",
                    },
                    {
                        "id": "other-user-task",
                        "user_id": "99999999-9999-4999-8999-999999999999",
                        "plan_id": PLAN_A_ID,
                        "scheduled_date": "2026-08-26",
                        "created_at": "2026-08-20T00:00:00+00:00",
                    },
                ]
            }
        )

        result = get_study_tasks_by_plan_ids(
            supabase=supabase,
            user_id=USER_ID,
            plan_ids=[PLAN_A_ID, PLAN_B_ID, PLAN_A_ID],
        )

        self.assertEqual(supabase.table_calls, ["study_tasks"])
        self.assertEqual([task["id"] for task in result[PLAN_A_ID]], ["task-a"])
        self.assertEqual([task["id"] for task in result[PLAN_B_ID]], ["task-b"])
        self.assertEqual(
            supabase.requests[0].in_filters,
            [("plan_id", [PLAN_A_ID, PLAN_B_ID])],
        )

    def test_empty_plan_list_does_not_query_database(self):
        supabase = FakeSupabase({"study_tasks": []})

        result = get_study_tasks_by_plan_ids(
            supabase=supabase,
            user_id=USER_ID,
            plan_ids=[],
        )

        self.assertEqual(result, {})
        self.assertEqual(supabase.table_calls, [])


if __name__ == "__main__":
    unittest.main()
