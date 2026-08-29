import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.quiz_repository import save_quiz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "supabase_learning_objective_quiz_links.sql"
VALIDATION_PATH = (
    PROJECT_ROOT / "supabase_learning_objective_quiz_links_validation.sql"
)
USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class LearningObjectiveQuizRepositoryTests(unittest.TestCase):
    @patch(
        "services.quiz_repository.build_quiz_concept_payload",
        return_value=[{"concept_key": "loops"}],
    )
    def test_save_quiz_passes_exactly_one_reference_id(self, _build_concepts):
        rpc_request = MagicMock()
        rpc_request.execute.return_value = FakeResponse(
            {
                "id": "quiz-id",
                "user_id": USER_ID,
                "learning_objective_id": "objective-id",
                "reference_learning_material_id": "source-id",
                "reference_review_material_id": None,
            }
        )
        supabase = MagicMock()
        supabase.rpc.return_value = rpc_request
        question = SimpleNamespace(
            model_dump=lambda: {"question": "반복 조건은?"}
        )
        quiz = SimpleNamespace(title="반복문 퀴즈", questions=[question])

        result = save_quiz(
            supabase=supabase,
            user_id=USER_ID,
            plan_id="plan-id",
            task_id="task-id",
            course_key="python",
            course_name="Python",
            quiz=quiz,
            reference_learning_material_id="source-id",
        )

        self.assertEqual(result["id"], "quiz-id")
        supabase.rpc.assert_called_once_with(
            "save_quiz_with_concepts",
            {
                "p_plan_id": "plan-id",
                "p_task_id": "task-id",
                "p_course_key": "python",
                "p_course_name": "Python",
                "p_title": "반복문 퀴즈",
                "p_questions": [{"question": "반복 조건은?"}],
                "p_concepts": [{"concept_key": "loops"}],
                "p_reference_learning_material_id": "source-id",
                "p_reference_review_material_id": None,
            },
        )

    def test_save_quiz_rejects_two_reference_ids(self):
        with self.assertRaisesRegex(ValueError, "하나만 선택"):
            save_quiz(
                supabase=MagicMock(),
                user_id=USER_ID,
                plan_id="plan-id",
                task_id="task-id",
                course_key="python",
                course_name="Python",
                quiz=SimpleNamespace(title="퀴즈", questions=[]),
                reference_learning_material_id="source-id",
                reference_review_material_id="review-id",
            )

    @patch(
        "services.quiz_repository.build_quiz_concept_payload",
        return_value=[],
    )
    def test_save_quiz_rejects_missing_objective_link(self, _build_concepts):
        rpc_request = MagicMock()
        rpc_request.execute.return_value = FakeResponse(
            {
                "id": "quiz-id",
                "user_id": USER_ID,
                "learning_objective_id": None,
                "reference_learning_material_id": None,
                "reference_review_material_id": None,
            }
        )
        supabase = MagicMock()
        supabase.rpc.return_value = rpc_request

        with self.assertRaisesRegex(RuntimeError, "학습목표"):
            save_quiz(
                supabase=supabase,
                user_id=USER_ID,
                plan_id="plan-id",
                task_id="task-id",
                course_key="python",
                course_name="Python",
                quiz=SimpleNamespace(title="퀴즈", questions=[]),
            )


class LearningObjectiveQuizMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        cls.validation = VALIDATION_PATH.read_text(encoding="utf-8").lower()

    def test_new_rpc_wraps_existing_atomic_quiz_save(self):
        self.assertIn("begin;", self.migration)
        self.assertIn("commit;", self.migration)
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("v_saved_quiz := public.save_quiz_with_concepts", self.migration)
        self.assertIn("update public.quizzes as quiz", self.migration)

    def test_server_derives_objective_and_validates_reference_ownership(self):
        self.assertIn("task.learning_objective_id", self.migration)
        self.assertIn("material.plan_id = p_plan_id", self.migration)
        self.assertIn("material.user_id = v_user_id", self.migration)
        self.assertIn(
            "v_reference_objective_id is distinct from v_task_objective_id",
            self.migration,
        )
        self.assertIn("objective_snapshot", self.migration)
        self.assertIn("objective_contract_hash", self.migration)

    def test_old_rpc_is_closed_and_new_rpc_is_authenticated_only(self):
        self.assertGreaterEqual(self.migration.count("revoke all on function"), 2)
        self.assertIn("from public, anon, authenticated", self.migration)
        self.assertIn("to authenticated", self.migration)

    def test_validation_is_read_only_and_checks_live_links(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("has_function_privilege", self.validation)
        self.assertIn(
            "is distinct from task.learning_objective_id",
            self.validation,
        )
        self.assertIn(
            "is distinct from quiz.learning_objective_id",
            self.validation,
        )
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
