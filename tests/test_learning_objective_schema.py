import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "supabase_learning_objectives_schema.sql"
VALIDATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objectives_schema_validation.sql"
)


class LearningObjectiveSchemaMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()

    def test_migration_is_transactional_and_enables_rls(self):
        self.assertIn("begin;", self.migration)
        self.assertIn("commit;", self.migration)
        self.assertIn(
            "alter table public.learning_objectives enable row level security",
            self.migration,
        )
        self.assertIn(
            "revoke all on public.learning_objectives",
            self.migration,
        )

    def test_learning_objective_contract_matches_python_model(self):
        self.assertIn(
            "create table public.learning_objectives",
            self.migration,
        )
        self.assertIn("objective_key ~ '^[a-z0-9]+(_[a-z0-9]+)*$'", self.migration)
        self.assertIn(
            "target_depth in ('foundation', 'developing', 'advanced')",
            self.migration,
        )
        self.assertIn("is not distinct from 'explain'", self.migration)
        self.assertIn("is not distinct from 'apply'", self.migration)
        self.assertIn("is not distinct from 'differentiate'", self.migration)
        self.assertIn("and contract_hash is not null", self.migration)
        self.assertIn("contract_hash ~ '^[0-9a-f]{64}$'", self.migration)

    def test_legacy_backfill_is_honest_and_links_existing_tasks(self):
        self.assertIn("'legacy_primary'", self.migration)
        self.assertIn("'legacy_backfill'", self.migration)
        self.assertIn("'기존 계획 전체 목표'", self.migration)
        self.assertIn("update public.study_tasks as task", self.migration)
        self.assertIn("set learning_objective_id = objective.id", self.migration)
        self.assertIn("contract_hash is null", self.migration)

    def test_compatibility_columns_remain_nullable(self):
        self.assertIn(
            "alter table public.study_tasks\nadd column learning_objective_id uuid;",
            self.migration,
        )
        self.assertIn(
            "alter table public.learning_materials\nadd column learning_objective_id uuid;",
            self.migration,
        )
        self.assertNotIn(
            "alter column learning_objective_id set not null",
            self.migration,
        )

    def test_quiz_tracks_at_most_one_reference_material(self):
        self.assertIn("reference_learning_material_id uuid", self.migration)
        self.assertIn("reference_review_material_id uuid", self.migration)
        self.assertIn("num_nonnulls(", self.migration)
        self.assertIn("<= 1", self.migration)

    def test_artifact_snapshot_requires_its_hash(self):
        self.assertGreaterEqual(
            self.migration.count("objective_snapshot is not null"),
            2,
        )
        self.assertGreaterEqual(
            self.migration.count("objective_contract_hash is not null"),
            2,
        )

    def test_validation_is_read_only_and_checks_backfill(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("relation.relrowsecurity", self.validation)
        self.assertIn("objective.objective_key = 'legacy_primary'", self.validation)
        self.assertIn("기존 과제의 호환 학습목표 연결", self.validation)
        self.assertIn("learning_objectives_plan_owner_fk", self.validation)


if __name__ == "__main__":
    unittest.main()
