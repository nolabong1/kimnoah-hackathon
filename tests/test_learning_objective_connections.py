import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from models.learning_objective import (
    LearningObjectiveContract,
    StoredLearningObjective,
)
from services.learning_objective_connection_service import (
    build_learning_objective_connection_report,
)
from services.learning_objective_repository import (
    get_learning_objective_connection_data,
)
from services.learning_objective_service import (
    calculate_learning_objective_hash,
)
from views.learning_objective_connections_ui import (
    render_learning_objective_connections,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
FIRST_OBJECTIVE_ID = "33333333-3333-4333-8333-333333333333"
SECOND_OBJECTIVE_ID = "44444444-4444-4444-8444-444444444444"


def _stored_objective(
    objective_id: str,
    objective_key: str,
    title: str,
    sort_order: int,
) -> StoredLearningObjective:
    contract = LearningObjectiveContract.model_validate(
        {
            "objective_key": objective_key,
            "title": title,
            "description": f"{title}을 설명하고 적용한다.",
            "target_depth": "developing",
            "evidence_requirements": [
                {"key": "explain", "description": "개념을 설명한다."},
                {"key": "apply", "description": "문제에 적용한다."},
                {
                    "key": "differentiate",
                    "description": "오해와 올바른 적용을 구분한다.",
                },
            ],
        }
    )
    return StoredLearningObjective.model_validate(
        {
            **contract.model_dump(mode="json"),
            "id": objective_id,
            "user_id": USER_ID,
            "plan_id": PLAN_ID,
            "contract_hash": calculate_learning_objective_hash(contract),
            "sort_order": sort_order,
            "origin": "generated",
        }
    )


def _objective_row(objective: StoredLearningObjective) -> dict:
    return objective.model_dump(mode="json")


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeQuery:
    def __init__(self, table_name, rows, selected_fields):
        self.table_name = table_name
        self.rows = deepcopy(rows)
        self.selected_fields = selected_fields
        self.filters = []
        self.plan_ids = None

    def select(self, fields):
        self.selected_fields[self.table_name] = fields
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        if field == "plan_id":
            self.plan_ids = {str(value) for value in values}
        return self

    def order(self, _field):
        return self

    def execute(self):
        rows = [
            row
            for row in self.rows
            if all(
                str(row.get(field)) == str(value)
                for field, value in self.filters
            )
            and (
                self.plan_ids is None
                or str(row.get("plan_id")) in self.plan_ids
            )
        ]
        return FakeResponse(rows)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables
        self.requested_tables = []
        self.selected_fields = {}

    def table(self, table_name):
        self.requested_tables.append(table_name)
        return FakeQuery(
            table_name,
            self.tables.get(table_name, []),
            self.selected_fields,
        )


class LearningObjectiveConnectionServiceTests(unittest.TestCase):
    def test_report_groups_records_in_objective_order(self):
        first = _stored_objective(
            FIRST_OBJECTIVE_ID,
            "python_conditions",
            "조건문",
            1,
        )
        second = _stored_objective(
            SECOND_OBJECTIVE_ID,
            "python_loops",
            "반복문",
            2,
        )

        report = build_learning_objective_connection_report(
            objectives=[second, first],
            tasks=[
                {
                    "title": "조건문 학습",
                    "learning_objective_id": FIRST_OBJECTIVE_ID,
                },
                {
                    "title": "이전 과제",
                    "learning_objective_id": None,
                },
            ],
            learning_materials=[
                {
                    "id": "source-id",
                    "title": "조건문 원본",
                    "learning_objective_id": FIRST_OBJECTIVE_ID,
                }
            ],
            review_materials=[
                {
                    "title": "반복문 AI 자료",
                    "learning_objective_id": SECOND_OBJECTIVE_ID,
                }
            ],
            quizzes=[
                {
                    "title": "조건문 확인 퀴즈",
                    "learning_objective_id": FIRST_OBJECTIVE_ID,
                    "reference_learning_material_id": "source-id",
                    "reference_review_material_id": None,
                },
                {
                    "title": "이전 퀴즈",
                    "learning_objective_id": None,
                },
            ],
        )

        self.assertEqual(
            [summary.objective.title for summary in report.summaries],
            ["조건문", "반복문"],
        )
        self.assertEqual(report.summaries[0].task_titles, ["조건문 학습"])
        self.assertEqual(
            report.summaries[0].source_material_titles,
            ["조건문 원본"],
        )
        self.assertEqual(
            report.summaries[1].review_material_titles,
            ["반복문 AI 자료"],
        )
        self.assertEqual(
            report.summaries[0].quiz_titles,
            ["조건문 확인 퀴즈 · 참고: 조건문 원본"],
        )
        self.assertEqual(report.unlinked_task_count, 1)
        self.assertEqual(report.unlinked_quiz_count, 1)

    def test_duplicate_task_titles_still_count_as_separate_tasks(self):
        objective = _stored_objective(
            FIRST_OBJECTIVE_ID,
            "python_conditions",
            "조건문",
            1,
        )
        duplicate_tasks = [
            {
                "title": "조건문 학습",
                "learning_objective_id": FIRST_OBJECTIVE_ID,
            },
            {
                "title": " 조건문 학습 ",
                "learning_objective_id": FIRST_OBJECTIVE_ID,
            },
        ]

        report = build_learning_objective_connection_report(
            objectives=[objective],
            tasks=duplicate_tasks,
            learning_materials=[],
            review_materials=[],
            quizzes=[],
        )

        self.assertEqual(
            report.summaries[0].task_titles,
            ["조건문 학습", "조건문 학습"],
        )


class LearningObjectiveConnectionRepositoryTests(unittest.TestCase):
    def test_connection_query_uses_owned_minimum_fields(self):
        objective = _stored_objective(
            FIRST_OBJECTIVE_ID,
            "python_conditions",
            "조건문",
            1,
        )
        owned_row = {
            "id": "record-id",
            "user_id": USER_ID,
            "plan_id": PLAN_ID,
            "title": "연결 항목",
            "learning_objective_id": FIRST_OBJECTIVE_ID,
        }
        supabase = FakeSupabase(
            {
                "learning_objectives": [_objective_row(objective)],
                "learning_materials": [owned_row],
                "review_materials": [owned_row],
                "quizzes": [owned_row],
            }
        )

        result = get_learning_objective_connection_data(
            supabase=supabase,
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        self.assertEqual(len(result["objectives"]), 1)
        self.assertEqual(
            supabase.requested_tables,
            [
                "learning_objectives",
                "learning_materials",
                "review_materials",
                "quizzes",
            ],
        )
        self.assertNotIn(
            "content_text",
            supabase.selected_fields["learning_materials"],
        )
        self.assertNotIn(
            "content_markdown",
            supabase.selected_fields["review_materials"],
        )

    @patch(
        "services.learning_objective_repository.get_learning_objectives_by_plan_ids"
    )
    def test_connection_query_rejects_foreign_owned_rows(
        self,
        get_objectives,
    ):
        objective = _stored_objective(
            FIRST_OBJECTIVE_ID,
            "python_conditions",
            "조건문",
            1,
        )
        get_objectives.return_value = {PLAN_ID: [objective]}
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.execute.return_value = FakeResponse(
            [
                {
                    "id": "foreign-record",
                    "user_id": "99999999-9999-4999-8999-999999999999",
                    "plan_id": PLAN_ID,
                    "title": "다른 사용자 자료",
                    "learning_objective_id": FIRST_OBJECTIVE_ID,
                }
            ]
        )
        supabase = MagicMock()
        supabase.table.return_value = query

        with self.assertRaisesRegex(RuntimeError, "소유권"):
            get_learning_objective_connection_data(
                supabase=supabase,
                user_id=USER_ID,
                plan_id=PLAN_ID,
            )


class LearningObjectiveConnectionViewTests(unittest.TestCase):
    @patch(
        "views.learning_objective_connections_ui.get_learning_objective_connection_data"
    )
    @patch("views.learning_objective_connections_ui.st.toggle", return_value=False)
    def test_closed_toggle_does_not_query_database(
        self,
        _toggle,
        get_connection_data,
    ):
        render_learning_objective_connections(
            supabase=MagicMock(),
            user_id=USER_ID,
            plan_id=PLAN_ID,
            tasks=[],
        )

        get_connection_data.assert_not_called()


if __name__ == "__main__":
    unittest.main()
