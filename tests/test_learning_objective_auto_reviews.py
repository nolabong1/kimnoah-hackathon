import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objective_auto_reviews.sql"
)
VALIDATION_PATH = (
    PROJECT_ROOT
    / "supabase_learning_objective_auto_reviews_validation.sql"
)
INTEGRATION_PATH = (
    PROJECT_ROOT
    / "supabase_learning_objective_integration_validation.sql"
)


class LearningObjectiveAutoReviewMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()
        cls.integration = INTEGRATION_PATH.read_text(encoding="utf-8").lower()

    def test_trigger_derives_objective_from_owned_quiz_attempt(self):
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("quiz.id = new.source_quiz_id", self.migration)
        self.assertIn(
            "attempt.id = new.source_quiz_attempt_id",
            self.migration,
        )
        self.assertIn("quiz.plan_id = new.plan_id", self.migration)
        self.assertIn("quiz.user_id = new.user_id", self.migration)
        self.assertIn("quiz_task.task_type = 'quiz'", self.migration)
        self.assertIn(
            "v_learning_objective_id := coalesce(",
            self.migration,
        )
        self.assertIn(
            "v_quiz_objective_id is distinct from v_quiz_task_objective_id",
            self.migration,
        )

    def test_insert_and_link_update_triggers_are_separate(self):
        self.assertIn("before insert\non public.study_tasks", self.migration)
        self.assertIn("before update of", self.migration)
        self.assertIn("source_quiz_attempt_id", self.migration)
        self.assertIn("learning_objective_id", self.migration)
        self.assertEqual(
            self.migration.count(
                "execute function public.sync_auto_review_learning_objective()"
            ),
            2,
        )

    def test_existing_reviews_are_backfilled_with_owned_relationships(self):
        update_position = self.migration.index("update public.study_tasks")
        commit_position = self.migration.rindex("commit;")

        self.assertLess(update_position, commit_position)
        self.assertIn(
            "where review_task.source_type = 'weakness_review'",
            self.migration,
        )
        self.assertIn("from public.quizzes as quiz", self.migration)
        self.assertIn("attempt.id = review_task.source_quiz_attempt_id", self.migration)

    def test_update_trigger_avoids_objective_fk_delete_updates(self):
        update_trigger = self.migration.split("before update of", 1)[1].split(
            "on public.study_tasks",
            1,
        )[0]

        self.assertNotIn("learning_objective_id", update_trigger)

    def test_trigger_function_is_not_client_callable(self):
        self.assertIn(
            "revoke all on function public.sync_auto_review_learning_objective()",
            self.migration,
        )
        self.assertIn("from public, anon, authenticated", self.migration)

    def test_validation_is_read_only_and_checks_live_inheritance(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("has_function_privilege", self.validation)
        self.assertIn("trigger.tgenabled <> 'd'", self.validation)
        self.assertIn("review_task.learning_objective_id is null", self.validation)
        self.assertIn(
            "review_task.learning_objective_id is distinct from coalesce(",
            self.validation,
        )
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))

    def test_integration_check_covers_complete_learning_chain(self):
        self.assertIn("set transaction read only", self.integration)
        self.assertIn("public.learning_objectives", self.integration)
        self.assertIn("public.study_tasks", self.integration)
        self.assertIn("public.learning_materials", self.integration)
        self.assertIn("public.review_materials", self.integration)
        self.assertIn("public.quizzes", self.integration)
        self.assertIn("source_type = 'weakness_review'", self.integration)
        self.assertIn("reference_learning_material_id", self.integration)
        self.assertIn("reference_review_material_id", self.integration)
        self.assertTrue(self.integration.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
