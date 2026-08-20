import unittest
from copy import deepcopy

from services.concept_mastery_repository import (
    MAX_RECENT_DIAGNOSIS_EVENTS_PER_CONCEPT,
    get_course_concept_masteries,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
CONCEPT_ID = "22222222-2222-4222-8222-222222222222"


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeTableRequest:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.limit_count = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def in_(self, field, values):
        allowed_values = set(values)
        self.rows = [
            row for row in self.rows if row.get(field) in allowed_values
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
            rows = rows[: self.limit_count]
        return FakeResponse(rows)


class FakeRpcRequest:
    def __init__(self, data):
        self.data = deepcopy(data)

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, table_rows, rpc_results):
        self.table_rows = table_rows
        self.rpc_results = rpc_results

    def table(self, name):
        return FakeTableRequest(self.table_rows.get(name, []))

    def rpc(self, name, params=None):
        return FakeRpcRequest(self.rpc_results.get(name))


class ConceptDiagnosisRepositoryTests(unittest.TestCase):
    def test_course_mastery_contains_only_five_latest_valid_diagnoses(self):
        diagnosis_types = [
            "boundary_error",
            "condition_omission",
            "boundary_error",
            "condition_omission",
            "concept_confusion",
            "concept_confusion",
            "invalid_type",
        ]
        events = [
            {
                "user_id": USER_ID,
                "concept_id": CONCEPT_ID,
                "is_correct": False,
                "diagnosis_type": diagnosis_type,
                "created_at": f"2026-08-20T00:00:{59 - index:02d}+00:00",
            }
            for index, diagnosis_type in enumerate(diagnosis_types)
        ]
        supabase = FakeSupabase(
            table_rows={
                "learning_concepts": [
                    {
                        "id": CONCEPT_ID,
                        "user_id": USER_ID,
                        "course_key": "python",
                        "concept_key": "python_range",
                        "canonical_name": "Python range 경계값",
                    }
                ],
                "concept_mastery": [
                    {
                        "user_id": USER_ID,
                        "concept_id": CONCEPT_ID,
                        "mastery_score": 45,
                        "correct_count": 1,
                        "incorrect_count": 6,
                        "consecutive_incorrect_count": 2,
                        "last_answer_correct": False,
                        "last_assessed_at": "2026-08-20T00:01:00+00:00",
                    }
                ],
                "concept_mastery_events": events,
            },
            rpc_results={"get_current_weak_concepts": []},
        )

        result = get_course_concept_masteries(
            supabase,
            USER_ID,
            "python",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["recent_diagnosis_types"],
            diagnosis_types[:MAX_RECENT_DIAGNOSIS_EVENTS_PER_CONCEPT],
        )


if __name__ == "__main__":
    unittest.main()
