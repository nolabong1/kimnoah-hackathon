import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class QuizDiagnosisPersonalizationSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = (
            PROJECT_ROOT / "supabase_quiz_diagnosis_personalization.sql"
        ).read_text(encoding="utf-8").casefold()
        cls.validation = (
            PROJECT_ROOT
            / "supabase_quiz_diagnosis_personalization_validation.sql"
        ).read_text(encoding="utf-8").casefold()

    def test_migration_adds_constrained_nullable_diagnosis(self):
        self.assertIn("add column if not exists diagnosis_type text", self.migration)
        self.assertIn(
            "concept_mastery_events_diagnosis_type_check",
            self.migration,
        )
        self.assertIn("not is_correct", self.migration)
        self.assertNotIn("'correct_reasoning'", self.migration)

    def test_server_trigger_uses_saved_attempt_snapshot(self):
        self.assertIn(
            "create trigger set_concept_mastery_event_diagnosis",
            self.migration,
        )
        self.assertIn("attempt.questions_snapshot", self.migration)
        self.assertIn("attempt.answers", self.migration)
        self.assertIn("before insert on public.concept_mastery_events", self.migration)

    def test_internal_trigger_function_is_not_client_callable(self):
        self.assertIn(
            "revoke all on function public.set_concept_mastery_event_diagnosis()",
            self.migration,
        )
        self.assertIn("from public, anon, authenticated", self.migration)
        self.assertIn("has_function_privilege", self.validation)

    def test_migration_backfills_only_supported_wrong_answers(self):
        self.assertIn("where not event.is_correct", self.migration)
        self.assertIn("event.diagnosis_type is null", self.migration)
        self.assertIn("candidate.diagnosis_type in", self.migration)


if __name__ == "__main__":
    unittest.main()
