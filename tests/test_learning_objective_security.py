import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "supabase_learning_objectives_security.sql"
VALIDATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objectives_security_validation.sql"
)


class LearningObjectiveSecurityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()

    def test_migration_is_transactional(self):
        self.assertIn("begin;", self.migration)
        self.assertIn("commit;", self.migration)
        self.assertIn("set local lock_timeout", self.migration)

    def test_objectives_are_read_only_for_authenticated_clients(self):
        self.assertIn("learning_objectives_select_own", self.migration)
        self.assertIn("using ((select auth.uid()) = user_id)", self.migration)
        self.assertIn(
            "revoke all on public.learning_objectives",
            self.migration,
        )
        self.assertIn(
            "grant select on public.learning_objectives to authenticated",
            self.migration,
        )
        self.assertNotIn(
            "grant insert on public.learning_objectives",
            self.migration,
        )

    def test_every_objective_link_uses_composite_ownership(self):
        for table_name in (
            "study_tasks",
            "learning_materials",
            "review_materials",
            "quizzes",
        ):
            self.assertIn(
                f"alter table public.{table_name}\n"
                f"add constraint {table_name}_objective_owner_fk",
                self.migration,
            )

        self.assertGreaterEqual(
            self.migration.count(
                "foreign key (learning_objective_id, plan_id, user_id)"
            ),
            4,
        )
        self.assertGreaterEqual(
            self.migration.count(
                "references public.learning_objectives(id, plan_id, user_id)"
            ),
            4,
        )

    def test_quiz_reference_links_use_composite_ownership(self):
        self.assertIn(
            "quizzes_reference_learning_material_owner_fk",
            self.migration,
        )
        self.assertIn(
            "foreign key (reference_learning_material_id, plan_id, user_id)",
            self.migration,
        )
        self.assertIn(
            "quizzes_reference_review_material_owner_fk",
            self.migration,
        )
        self.assertIn(
            "foreign key (reference_review_material_id, plan_id, user_id)",
            self.migration,
        )

    def test_optional_links_are_cleared_without_deleting_artifacts(self):
        self.assertGreaterEqual(
            self.migration.count("on delete set null"),
            6,
        )
        self.assertNotIn("alter column learning_objective_id set not null", self.migration)

    def test_query_indexes_cover_objectives_and_references(self):
        expected_indexes = (
            "learning_objectives_user_plan_order_idx",
            "study_tasks_plan_objective_date_idx",
            "learning_materials_plan_objective_created_idx",
            "review_materials_plan_objective_updated_idx",
            "quizzes_plan_objective_updated_idx",
            "quizzes_reference_learning_material_idx",
            "quizzes_reference_review_material_idx",
        )
        for index_name in expected_indexes:
            self.assertIn(f"create index {index_name}", self.migration)

    def test_validation_is_read_only_and_checks_live_constraints(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("constraint_record.convalidated", self.validation)
        self.assertIn("constraint_record.confdeltype <> 'n'", self.validation)
        self.assertIn("learning_objectives_plan_key_unique", self.validation)
        self.assertIn("learning_objectives_plan_order_unique", self.validation)
        self.assertIn("quizzes_single_reference_material_check", self.validation)
        self.assertIn("review_materials_task_unique", self.validation)
        self.assertIn("pg_catalog.has_table_privilege", self.validation)
        self.assertIn("pg_catalog.pg_indexes", self.validation)
        self.assertIn("rollback;", self.validation)


if __name__ == "__main__":
    unittest.main()
