import unittest
from copy import deepcopy
from pathlib import Path

from tools.validate_sql_migrations import (
    DEFAULT_MANIFEST_PATH,
    load_manifest,
    render_execution_plan,
    validate_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SqlMigrationManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()

    def test_current_manifest_classifies_every_sql_file(self):
        errors = validate_manifest(self.manifest)

        self.assertEqual(errors, [])
        migration_count = len(self.manifest["migrations"])
        validation_count = sum(
            "validation" in migration
            for migration in self.manifest["migrations"]
        )
        standalone_count = len(self.manifest["standalone_checks"])
        self.assertEqual(
            len(list(PROJECT_ROOT.glob("supabase_*.sql"))),
            migration_count + validation_count + standalone_count,
        )

    def test_execution_plan_starts_with_schema_and_ends_with_checks(self):
        plan = render_execution_plan(self.manifest).splitlines()

        self.assertEqual(plan[0], "001  supabase_schema.sql")
        self.assertIn(
            "031  supabase_dashboard_snapshot.sql  ->  "
            "supabase_dashboard_snapshot_validation.sql",
            plan,
        )
        self.assertTrue(plan[-1].startswith("CHECK after "))

    def test_reordered_dependency_is_rejected(self):
        invalid_manifest = deepcopy(self.manifest)
        invalid_manifest["migrations"][1]["depends_on"] = []

        errors = validate_manifest(invalid_manifest)

        self.assertTrue(any("depends_on" in error for error in errors))

    def test_missing_manifest_file_is_rejected(self):
        invalid_manifest = deepcopy(self.manifest)
        invalid_manifest["migrations"][-1]["path"] = "missing.sql"

        errors = validate_manifest(invalid_manifest)

        self.assertTrue(any("파일을 찾을 수 없습니다" in error for error in errors))
        self.assertTrue(any("분류되지 않은 SQL" in error for error in errors))

    def test_integration_check_must_follow_latest_migration(self):
        invalid_manifest = deepcopy(self.manifest)
        invalid_manifest["standalone_checks"][0]["after"] = (
            "030_core_write_boundary"
        )

        errors = validate_manifest(invalid_manifest)

        self.assertTrue(any("마지막 migration" in error for error in errors))

    def test_manifest_path_is_canonical(self):
        self.assertEqual(
            DEFAULT_MANIFEST_PATH,
            PROJECT_ROOT / "supabase" / "migrations.toml",
        )


if __name__ == "__main__":
    unittest.main()
