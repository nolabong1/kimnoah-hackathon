import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from models.learning_objective import StoredLearningObjective
from models.mock_exam import GeneratedMockExam, MockExamDraft
from services.mock_exam_repository import (
    get_mock_exam_state,
    get_mock_exams_by_plan,
    save_mock_exam,
    submit_mock_exam_attempt,
)
from services.mock_exam_service import (
    build_mock_exam_blueprint,
    generate_mock_exam,
    validate_mock_exam_against_blueprint,
)
from views.mock_exam_state import (
    MOCK_EXAM_PREFIX,
    clear_mock_exam_state,
    get_generated_mock_exam,
    get_or_create_submission_request,
    store_generated_mock_exam,
)


USER_ID = "5441d349-a86d-4ed7-a67c-ae1048f1ad08"
PLAN_ID = "3a3a5116-39bb-4747-a9ad-99f1c402c360"
EXAM_ID = "9bd28f68-f30f-47f1-8dfc-8e8afe1082d5"
GENERATION_KEY = "5d1cb4dc-ed5d-4f43-8cdc-f9c2f2786e2f"
SUBMISSION_KEY = "b92cf00c-b22a-449e-a50b-cda26881336d"
EVIDENCE_KEYS = ["explain", "apply", "differentiate"]


def _objectives(count: int = 2) -> list[StoredLearningObjective]:
    ids = [
        "9f62e9e4-5b35-4ef9-8c10-795c5f8d49c0",
        "03182717-dfd3-45d1-99b1-5bf603398703",
        "7e520c28-a6df-4e6c-8635-48b076609814",
        "f4c849b1-9e62-4246-a70e-cb5d283ef7a3",
        "02d37d4e-6a25-4aa4-b18a-62df4d9fd31e",
    ]
    return [
        StoredLearningObjective.model_validate(
            {
                "id": ids[index - 1],
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "objective_key": f"objective_{index}",
                "title": f"학습목표 {index}",
                "description": f"학습목표 {index}을 설명하고 적용합니다.",
                "target_depth": "developing",
                "evidence_requirements": [
                    {"key": key, "description": f"{key} 성공 기준"}
                    for key in EVIDENCE_KEYS
                ],
                "contract_hash": str(index) * 64,
                "sort_order": index,
                "origin": "generated",
            }
        )
        for index in range(1, count + 1)
    ]


def _exam_payload(objectives=None, *, source=False) -> dict:
    objectives = objectives or _objectives()
    questions = []
    for slot in build_mock_exam_blueprint(objectives):
        question_number = slot["question_number"]
        questions.append(
            {
                "question": f"모의 평가 {question_number}번 문제는 무엇인가요?",
                "choices": [
                    f"{question_number}번 선택지 {choice_number}"
                    for choice_number in range(1, 5)
                ],
                "correct_answer_index": question_number % 4,
                "explanation": "정답을 판단하는 구체적인 근거입니다.",
                "objective_key": slot["objective_key"],
                "evidence_key": slot["evidence_key"],
                "difficulty": slot["difficulty"],
                "source_title": "선택 자료" if source else None,
                "source_evidence": "반복문은 조건을 확인하며 실행됩니다." if source else None,
            }
        )
    return {
        "title": "Python 시험 대비 모의 평가",
        "recommended_minutes": 30,
        "questions": questions,
    }


def _attempt_payload() -> dict:
    objectives = _objectives()
    exam = _exam_payload(objectives)
    objective_counts = {item.objective_key: 0 for item in objectives}
    question_results = []
    for index, question in enumerate(exam["questions"]):
        objective_counts[question["objective_key"]] += 1
        correct_index = question["correct_answer_index"]
        question_results.append(
            {
                "question_index": index,
                "objective_key": question["objective_key"],
                "evidence_key": question["evidence_key"],
                "difficulty": question["difficulty"],
                "selected_answer_index": correct_index,
                "correct_answer_index": correct_index,
                "is_correct": True,
                "explanation": question["explanation"],
                "source_title": None,
                "source_evidence": None,
            }
        )
    return {
        "attempt_id": "7e520c28-a6df-4e6c-8635-48b076609814",
        "mock_exam_id": EXAM_ID,
        "submission_key": SUBMISSION_KEY,
        "attempt_number": 1,
        "correct_count": 15,
        "total_questions": 15,
        "score": 100,
        "objective_scores": [
            {
                "objective_key": key,
                "correct_count": count,
                "total_questions": count,
                "score": 100,
            }
            for key, count in objective_counts.items()
        ],
        "question_results": question_results,
        "submitted_at": "2026-09-05T12:00:00+09:00",
        "already_processed": False,
    }


def _state_payload() -> dict:
    exam = _exam_payload()
    return {
        "user_id": USER_ID,
        "plan_id": PLAN_ID,
        "exam_id": EXAM_ID,
        "title": exam["title"],
        "recommended_minutes": 30,
        "objective_snapshot": [
            {"objective_key": item.objective_key, "title": item.title}
            for item in _objectives()
        ],
        "questions": [
            {
                key: value
                for key, value in question.items()
                if key
                not in {
                    "correct_answer_index",
                    "explanation",
                    "source_title",
                    "source_evidence",
                }
            }
            for question in exam["questions"]
        ],
        "attempt_count": 1,
        "best_score": 100,
        "attempt_history": [
            {
                "attempt_number": 1,
                "correct_count": 15,
                "score": 100,
                "submitted_at": "2026-09-05T12:00:00+09:00",
            }
        ],
        "latest_attempt": _attempt_payload(),
        "created_at": "2026-09-05T10:00:00+09:00",
    }


class FakeResponses:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed_output)


class FakeOpenAIClient:
    def __init__(self, parsed_output):
        self.responses = FakeResponses(parsed_output)


class FakeRpcClient:
    def __init__(self, response_data):
        self.response_data = response_data
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return self

    def execute(self):
        return SimpleNamespace(data=self.response_data)


class MockExamModelAndServiceTests(unittest.TestCase):
    def test_blueprint_balances_objectives_evidence_and_difficulty(self):
        blueprint = build_mock_exam_blueprint(_objectives(5))

        self.assertEqual(len(blueprint), 15)
        for objective_number in range(1, 6):
            objective_slots = [
                item
                for item in blueprint
                if item["objective_key"] == f"objective_{objective_number}"
            ]
            self.assertEqual(len(objective_slots), 3)
            self.assertEqual(
                [item["evidence_key"] for item in objective_slots],
                EVIDENCE_KEYS,
            )
        difficulties = [item["difficulty"] for item in blueprint]
        self.assertEqual(difficulties.count("easy"), 4)
        self.assertEqual(difficulties.count("medium"), 7)
        self.assertEqual(difficulties.count("hard"), 4)

    def test_exam_requires_exactly_fifteen_unique_questions(self):
        payload = _exam_payload()
        exam = MockExamDraft.model_validate(payload)
        self.assertEqual(len(exam.questions), 15)

        with self.assertRaises(ValidationError):
            MockExamDraft.model_validate({**payload, "questions": payload["questions"][:14]})

    def test_blueprint_validation_rejects_reordered_objective(self):
        exam = MockExamDraft.model_validate(_exam_payload())
        exam.questions[0].objective_key = "objective_2"

        with self.assertRaisesRegex(ValueError, "출제 설계"):
            validate_mock_exam_against_blueprint(exam, _objectives())

    @patch("services.mock_exam_service.get_openai_model", return_value="test-model")
    @patch("services.mock_exam_service.get_openai_client")
    def test_generation_uses_one_structured_request(
        self,
        get_client,
        _get_model,
    ):
        parsed = MockExamDraft.model_validate(_exam_payload())
        client = FakeOpenAIClient(parsed)
        get_client.return_value = client

        generated = generate_mock_exam(
            course_name="Python",
            goal="조건문과 반복문 시험 대비",
            current_level=5,
            objectives=_objectives(),
        )

        self.assertEqual(generated.exam.title, parsed.title)
        self.assertEqual(len(client.responses.calls), 1)
        self.assertIs(client.responses.calls[0]["text_format"], MockExamDraft)

    def test_reference_evidence_must_exist_in_selected_material(self):
        exam = MockExamDraft.model_validate(_exam_payload(source=True))

        with self.assertRaisesRegex(ValueError, "원문 근거"):
            validate_mock_exam_against_blueprint(
                exam,
                _objectives(),
                reference_title="선택 자료",
                reference_content="전혀 다른 원문입니다.",
            )


class MockExamRepositoryAndStateTests(unittest.TestCase):
    def test_repository_uses_dedicated_rpc_and_validates_owner(self):
        generated = GeneratedMockExam(
            exam=MockExamDraft.model_validate(_exam_payload()),
            prompt_version="mock_exam_v1",
            model_name="test-model",
        )
        client = FakeRpcClient(
            {
                "id": EXAM_ID,
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "generation_key": GENERATION_KEY,
                "already_processed": False,
            }
        )

        result = save_mock_exam(
            supabase=client,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            generation_key=GENERATION_KEY,
            generated=generated,
        )

        self.assertEqual(str(result.id), EXAM_ID)
        self.assertEqual(client.calls[0][0], "save_mock_exam")

    def test_catalog_state_and_submission_are_parsed(self):
        catalog_client = FakeRpcClient(
            [
                {
                    "id": EXAM_ID,
                    "user_id": USER_ID,
                    "plan_id": PLAN_ID,
                    "title": "Python 모의 평가",
                    "question_count": 15,
                    "recommended_minutes": 30,
                    "attempt_count": 1,
                    "best_score": 100,
                    "latest_score": 100,
                    "created_at": "2026-09-05T10:00:00+09:00",
                }
            ]
        )
        summaries = get_mock_exams_by_plan(
            supabase=catalog_client,
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )
        state_client = FakeRpcClient(_state_payload())
        state = get_mock_exam_state(
            supabase=state_client,
            user_id=USER_ID,
            exam_id=EXAM_ID,
        )
        attempt_client = FakeRpcClient(_attempt_payload())
        attempt = submit_mock_exam_attempt(
            supabase=attempt_client,
            user_id=USER_ID,
            exam_id=EXAM_ID,
            answers=[question["correct_answer_index"] for question in _exam_payload()["questions"]],
            submission_key=SUBMISSION_KEY,
        )

        self.assertEqual(summaries[0].latest_score, 100)
        self.assertEqual(state.attempt_count, 1)
        self.assertEqual(attempt.score, 100)
        self.assertEqual(attempt_client.calls[0][0], "submit_mock_exam_attempt")

    def test_session_requests_are_idempotent_and_reset_is_scoped(self):
        state = {"unrelated": "keep"}
        valid_generated = GeneratedMockExam(
            exam=MockExamDraft.model_validate(_exam_payload()),
            prompt_version="mock_exam_v1",
            model_name="test-model",
        )
        key = store_generated_mock_exam(
            state,
            plan_id=PLAN_ID,
            reference_key=None,
            generated=valid_generated,
        )
        self.assertEqual(
            get_generated_mock_exam(
                state,
                plan_id=PLAN_ID,
                reference_key=None,
            )[1],
            key,
        )
        first = get_or_create_submission_request(
            state,
            exam_id=EXAM_ID,
            answers=[0] * 15,
        )
        second = get_or_create_submission_request(
            state,
            exam_id=EXAM_ID,
            answers=[0] * 15,
        )
        self.assertEqual(first, second)
        clear_mock_exam_state(state)
        self.assertEqual(state, {"unrelated": "keep"})
        self.assertTrue(all(not key.startswith(MOCK_EXAM_PREFIX) for key in state))


class MockExamSqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).resolve().parents[1]
        cls.sql = (project_root / "supabase_mock_exams.sql").read_text(encoding="utf-8")
        cls.validation = (
            project_root / "supabase_mock_exams_validation.sql"
        ).read_text(encoding="utf-8")
        cls.manifest = (project_root / "supabase" / "migrations.toml").read_text(
            encoding="utf-8"
        )
        cls.app_source = (project_root / "app.py").read_text(encoding="utf-8")

    def test_schema_has_ownership_rls_and_idempotency_contracts(self):
        self.assertIn("create table public.mock_exams", self.sql)
        self.assertIn("create table public.mock_exam_attempts", self.sql)
        self.assertIn("mock_exams_plan_owner_fk", self.sql)
        self.assertIn("mock_exam_attempts_exam_owner_fk", self.sql)
        self.assertIn("mock_exams_generation_unique", self.sql)
        self.assertIn("mock_exam_attempts_submission_unique", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertIn("set search_path = ''", self.sql)

    def test_submission_does_not_mutate_rewards_tasks_or_mastery(self):
        submit_sql = self.sql.split(
            "create function public.submit_mock_exam_attempt", 1
        )[1]
        for forbidden in (
            "exp_events",
            "complete_study_task",
            "concept_mastery",
            "auto_review",
        ):
            self.assertNotIn(forbidden, submit_sql)

    def test_migration_is_registered_after_learning_assessments(self):
        self.assertIn('id = "041_mock_exams"', self.manifest)
        self.assertIn('depends_on = ["040_learning_assessments"]', self.manifest)
        self.assertIn("mock exam validation: success", self.validation)

    def test_navigation_and_logout_cleanup_are_connected(self):
        self.assertIn('title="시험 대비 모의 평가"', self.app_source)
        self.assertIn('url_path="mock-exam"', self.app_source)
        self.assertIn("clear_mock_exam_state(st.session_state)", self.app_source)


if __name__ == "__main__":
    unittest.main()
