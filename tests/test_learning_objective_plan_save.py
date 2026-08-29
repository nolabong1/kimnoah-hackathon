import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "supabase_learning_objective_plan_save.sql"
VALIDATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objective_plan_save_validation.sql"
)


class LearningObjectivePlanSaveMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()

    def test_plan_objectives_and_tasks_are_saved_in_one_rpc(self):
        self.assertIn("begin;", self.migration)
        self.assertIn("commit;", self.migration)
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("insert into public.study_plans", self.migration)
        self.assertIn("insert into public.learning_objectives", self.migration)
        self.assertIn("insert into public.study_tasks", self.migration)
        self.assertIn("learning_objective_id", self.migration)

    def test_server_revalidates_objective_contract_and_links(self):
        self.assertIn("not between 2 and 5", self.migration)
        self.assertIn("^[a-z0-9]+(_[a-z0-9]+)*$", self.migration)
        self.assertIn("is distinct from 'explain'", self.migration)
        self.assertIn("is distinct from 'apply'", self.migration)
        self.assertIn("is distinct from 'differentiate'", self.migration)
        self.assertIn("^[0-9a-f]{64}$", self.migration)
        self.assertIn("when p_current_level <= 3 then 'foundation'", self.migration)
        self.assertIn("과제가 존재하지 않는 학습목표", self.migration)
        self.assertIn("연결된 과제가 없는 학습목표", self.migration)

    def test_old_rpc_is_revoked_and_new_rpc_is_authenticated_only(self):
        self.assertGreaterEqual(self.migration.count("revoke all on function"), 2)
        self.assertIn("from public, anon, authenticated", self.migration)
        self.assertIn("to authenticated", self.migration)
        self.assertIn("이전 8인자 함수", self.migration)

    def test_validation_is_read_only_and_checks_runtime_contract(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("pg_catalog.has_function_privilege", self.validation)
        self.assertIn("learning_objective_count", self.validation)
        self.assertIn("origin = 'generated'", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
