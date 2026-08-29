import unittest
from copy import deepcopy
from pathlib import Path

from services.learning_objective_repository import (
    get_learning_objective_for_task,
    get_learning_objectives_by_plan_ids,
)
from services.learning_objective_service import (
    calculate_learning_objective_hash,
)
from models.learning_objective import LearningObjectiveContract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objective_material_links.sql"
)
VALIDATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objective_material_links_validation.sql"
)
USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
TASK_ID = "33333333-3333-4333-8333-333333333333"
OBJECTIVE_ID = "44444444-4444-4444-8444-444444444444"


def _objective_row() -> dict:
    contract = LearningObjectiveContract.model_validate(
        {
            "objective_key": "python_conditionals",
            "title": "조건문의 실행 흐름",
            "description": "조건식에 따른 분기 흐름을 설명하고 적용한다.",
            "target_depth": "developing",
            "evidence_requirements": [
                {"key": "explain", "description": "실행 흐름을 설명한다."},
                {"key": "apply", "description": "분기 코드를 작성한다."},
                {"key": "differentiate", "description": "분기 차이를 구분한다."},
            ],
        }
    )
    return {
        **contract.model_dump(mode="json"),
        "id": OBJECTIVE_ID,
        "user_id": USER_ID,
        "plan_id": PLAN_ID,
        "contract_hash": calculate_learning_objective_hash(contract),
        "sort_order": 1,
        "origin": "generated",
    }


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeQuery:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.filters = []
        self.plan_ids = None

    def select(self, _fields):
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

    def limit(self, _count):
        return self

    def execute(self):
        rows = [
            row
            for row in self.rows
            if all(str(row.get(field)) == str(value) for field, value in self.filters)
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

    def table(self, table_name):
        self.requested_tables.append(table_name)
        return FakeQuery(self.tables.get(table_name, []))


class LearningObjectiveRepositoryTests(unittest.TestCase):
    def test_multiple_plan_objectives_are_loaded_in_one_query(self):
        supabase = FakeSupabase({"learning_objectives": [_objective_row()]})

        grouped = get_learning_objectives_by_plan_ids(
            supabase,
            USER_ID,
            [PLAN_ID, PLAN_ID, ""],
        )

        self.assertEqual(len(grouped[PLAN_ID]), 1)
        self.assertEqual(supabase.requested_tables, ["learning_objectives"])

    def test_task_objective_is_rechecked_against_database_link(self):
        supabase = FakeSupabase(
            {
                "study_tasks": [
                    {
                        "id": TASK_ID,
                        "user_id": USER_ID,
                        "plan_id": PLAN_ID,
                        "learning_objective_id": OBJECTIVE_ID,
                    }
                ],
                "learning_objectives": [_objective_row()],
            }
        )

        objective = get_learning_objective_for_task(
            supabase,
            USER_ID,
            PLAN_ID,
            TASK_ID,
            OBJECTIVE_ID,
        )

        self.assertEqual(str(objective.id), OBJECTIVE_ID)
        self.assertEqual(
            supabase.requested_tables,
            ["study_tasks", "learning_objectives"],
        )

    def test_stale_task_objective_is_rejected(self):
        supabase = FakeSupabase(
            {
                "study_tasks": [
                    {
                        "id": TASK_ID,
                        "user_id": USER_ID,
                        "plan_id": PLAN_ID,
                        "learning_objective_id": OBJECTIVE_ID,
                    }
                ]
            }
        )

        with self.assertRaisesRegex(RuntimeError, "최신 DB 연결과 다릅니다"):
            get_learning_objective_for_task(
                supabase,
                USER_ID,
                PLAN_ID,
                TASK_ID,
                "55555555-5555-4555-8555-555555555555",
            )


class LearningObjectiveMaterialMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()

    def test_trigger_derives_objective_from_task_or_source(self):
        self.assertIn("before insert or update", self.migration)
        self.assertIn("new.task_id", self.migration)
        self.assertIn("new.source_material_id", self.migration)
        self.assertIn("new.learning_objective_id :=", self.migration)
        self.assertIn("objective_snapshot", self.migration)
        self.assertIn("objective_contract_hash", self.migration)

    def test_trigger_uses_safe_relation_names_and_is_not_client_callable(self):
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("public.study_tasks", self.migration)
        self.assertIn("public.learning_materials", self.migration)
        self.assertIn("public.learning_objectives", self.migration)
        self.assertIn("from public, anon, authenticated", self.migration)

    def test_validation_is_read_only_and_checks_live_links(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("trigger.tgenabled <> 'd'", self.validation)
        self.assertIn("is distinct from task.learning_objective_id", self.validation)
        self.assertIn("is distinct from source.learning_objective_id", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
