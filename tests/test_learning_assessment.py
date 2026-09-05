import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from models.learning_assessment import (
    GeneratedLearningAssessmentPair,
    LearningAssessmentAttemptResult,
    LearningAssessmentPairDraft,
    LearningAssessmentPlanState,
)
from models.learning_objective import StoredLearningObjective
from services.learning_assessment_repository import (
    get_learning_assessment_state,
    save_learning_assessment_pair,
    submit_learning_assessment_attempt,
)
from services.learning_assessment_service import (
    generate_learning_assessment_pair,
    validate_assessment_pair_against_objectives,
)
from views.learning_assessment_state import (
    LEARNING_ASSESSMENT_PREFIX,
    consume_pending_assessment_plan,
    get_or_create_submission_request,
    request_learning_assessment_navigation,
    clear_learning_assessment_state,
)


OBJECTIVE_KEYS = ["python_condition", "python_loop"]
EVIDENCE_KEYS = ["explain", "apply", "differentiate"]


def _question(
    phase: str,
    objective_key: str,
    evidence_key: str,
    index: int,
) -> dict:
    return {
        "question": (
            f"{phase} {objective_key} {evidence_key} 평가 문항 {index}은?"
        ),
        "choices": ["선택 1", "선택 2", "선택 3", "선택 4"],
        "correct_answer_index": index % 4,
        "explanation": "정답을 판단하는 근거를 설명합니다.",
        "objective_key": objective_key,
        "evidence_key": evidence_key,
        "target_depth": "foundation",
    }


def _form(phase: str) -> dict:
    questions = []
    for objective_key in OBJECTIVE_KEYS:
        for evidence_key in EVIDENCE_KEYS:
            questions.append(
                _question(
                    phase,
                    objective_key,
                    evidence_key,
                    len(questions),
                )
            )
    return {
        "phase": phase,
        "title": f"Python {phase} 평가",
        "questions": questions,
    }


def _valid_pair_payload() -> dict:
    return {
        "pre_assessment": _form("pre"),
        "post_assessment": _form("post"),
    }


def _attempt_payload() -> dict:
    question_results = []
    for index, objective_key in enumerate(
        [key for key in OBJECTIVE_KEYS for _ in range(3)]
    ):
        selected_answer_index = 0 if index < 3 else 1
        question_results.append(
            {
                "question_index": index,
                "objective_key": objective_key,
                "evidence_key": EVIDENCE_KEYS[index % 3],
                "selected_answer_index": selected_answer_index,
                "correct_answer_index": 0,
                "is_correct": index < 3,
                "explanation": "저장된 문항 해설입니다.",
            }
        )
    return {
        "attempt_id": "7e520c28-a6df-4e6c-8635-48b076609814",
        "assessment_id": "9bd28f68-f30f-47f1-8dfc-8e8afe1082d5",
        "phase": "pre",
        "submission_key": "5d1cb4dc-ed5d-4f43-8cdc-f9c2f2786e2f",
        "correct_count": 3,
        "total_questions": 6,
        "score": 50,
        "objective_scores": [
            {
                "objective_key": "python_condition",
                "correct_count": 3,
                "total_questions": 3,
                "score": 100,
            },
            {
                "objective_key": "python_loop",
                "correct_count": 0,
                "total_questions": 3,
                "score": 0,
            },
        ],
        "question_results": question_results,
        "submitted_at": "2026-09-05T10:00:00+09:00",
        "already_processed": False,
    }


def _form_state_payload(phase: str) -> dict:
    assessment_id = (
        "9bd28f68-f30f-47f1-8dfc-8e8afe1082d5"
        if phase == "pre"
        else "b92cf00c-b22a-449e-a50b-cda26881336d"
    )
    return {
        "id": assessment_id,
        "phase": phase,
        "title": f"Python {phase} 평가",
        "question_count": 6,
        "objective_snapshot": [
            {
                "objective_key": objective.objective_key,
                "title": objective.title,
            }
            for objective in _stored_objectives()
        ],
        "questions": [
            {
                key: value
                for key, value in question.items()
                if key not in {"correct_answer_index", "explanation"}
            }
            for question in _form(phase)["questions"]
        ],
        "created_at": "2026-09-05T09:00:00+09:00",
    }


def _stored_objectives() -> list[StoredLearningObjective]:
    return [
        StoredLearningObjective.model_validate(
            {
                "id": (
                    "9f62e9e4-5b35-4ef9-8c10-795c5f8d49c0"
                    if index == 1
                    else "03182717-dfd3-45d1-99b1-5bf603398703"
                ),
                "user_id": "5441d349-a86d-4ed7-a67c-ae1048f1ad08",
                "plan_id": "3a3a5116-39bb-4747-a9ad-99f1c402c360",
                "objective_key": objective_key,
                "title": f"학습목표 {index}",
                "description": f"{objective_key}를 설명하고 적용합니다.",
                "target_depth": "foundation",
                "evidence_requirements": [
                    {"key": key, "description": f"{key} 성공 기준"}
                    for key in EVIDENCE_KEYS
                ],
                "contract_hash": "a" * 64,
                "sort_order": index,
                "origin": "generated",
            }
        )
        for index, objective_key in enumerate(OBJECTIVE_KEYS, start=1)
    ]


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


class LearningAssessmentDraftTests(unittest.TestCase):
    def test_parallel_forms_share_ordered_measurement_contract(self):
        pair = LearningAssessmentPairDraft.model_validate(
            _valid_pair_payload()
        )

        self.assertEqual(len(pair.pre_assessment.questions), 6)
        self.assertEqual(
            pair.pre_assessment.measurement_slots(),
            pair.post_assessment.measurement_slots(),
        )
        self.assertEqual(
            [
                question.evidence_key
                for question in pair.pre_assessment.questions[:3]
            ],
            EVIDENCE_KEYS,
        )

    def test_form_rejects_missing_or_reordered_evidence_slot(self):
        payload = _valid_pair_payload()
        questions = payload["pre_assessment"]["questions"]
        questions[0], questions[1] = questions[1], questions[0]

        with self.assertRaisesRegex(
            ValidationError,
            "explain, apply, differentiate",
        ):
            LearningAssessmentPairDraft.model_validate(payload)

    def test_pair_rejects_different_target_depth(self):
        payload = _valid_pair_payload()
        for question in payload["post_assessment"]["questions"][:3]:
            question["target_depth"] = "developing"

        with self.assertRaisesRegex(
            ValidationError,
            "같은 학습목표, 성공 기준과 깊이",
        ):
            LearningAssessmentPairDraft.model_validate(payload)

    def test_pair_rejects_reused_question_between_forms(self):
        payload = _valid_pair_payload()
        payload["post_assessment"]["questions"][0]["question"] = (
            "  PRE   python_condition explain 평가 문항 0은?  "
        )

        with self.assertRaisesRegex(
            ValidationError,
            "서로 다른 문항",
        ):
            LearningAssessmentPairDraft.model_validate(payload)

    def test_pair_rejects_wrong_phase(self):
        payload = _valid_pair_payload()
        payload["pre_assessment"]["phase"] = "post"

        with self.assertRaisesRegex(
            ValidationError,
            "사전 평가의 단계는 pre",
        ):
            LearningAssessmentPairDraft.model_validate(payload)

    def test_question_rejects_duplicate_choices(self):
        payload = _valid_pair_payload()
        payload["pre_assessment"]["questions"][0]["choices"] = [
            "같은 답",
            "같은 답",
            "다른 답",
            "또 다른 답",
        ]

        with self.assertRaisesRegex(ValidationError, "서로 달라야"):
            LearningAssessmentPairDraft.model_validate(payload)


class LearningAssessmentAttemptResultTests(unittest.TestCase):
    def _attempt_payload(self) -> dict:
        return _attempt_payload()

    def test_attempt_result_accepts_consistent_server_totals(self):
        result = LearningAssessmentAttemptResult.model_validate(
            self._attempt_payload()
        )

        self.assertEqual(result.score, 50)
        self.assertEqual(len(result.objective_scores), 2)

    def test_attempt_result_rejects_inconsistent_score(self):
        payload = self._attempt_payload()
        payload["score"] = 60

        with self.assertRaisesRegex(
            ValidationError,
            "평가 점수가 정답 수와 일치하지 않습니다",
        ):
            LearningAssessmentAttemptResult.model_validate(payload)

    def test_attempt_result_rejects_inconsistent_question_correctness(self):
        payload = self._attempt_payload()
        payload["question_results"][0]["is_correct"] = False

        with self.assertRaisesRegex(
            ValidationError,
            "문항 정오답 결과",
        ):
            LearningAssessmentAttemptResult.model_validate(payload)

    def test_attempt_result_uses_database_compatible_half_up_rounding(self):
        payload = self._attempt_payload()
        third_objective = "python_function"
        for index in range(6, 9):
            payload["question_results"].append(
                {
                    "question_index": index,
                    "objective_key": third_objective,
                    "evidence_key": EVIDENCE_KEYS[index % 3],
                    "selected_answer_index": 1,
                    "correct_answer_index": 0,
                    "is_correct": False,
                    "explanation": "저장된 문항 해설입니다.",
                }
            )
        payload["objective_scores"].append(
            {
                "objective_key": third_objective,
                "correct_count": 0,
                "total_questions": 3,
                "score": 0,
            }
        )
        payload["total_questions"] = 9
        payload["score"] = 33

        result = LearningAssessmentAttemptResult.model_validate(payload)

        self.assertEqual(result.score, 33)

    def test_attempt_result_rejects_missing_question_index(self):
        payload = self._attempt_payload()
        payload["question_results"][5]["question_index"] = 6

        with self.assertRaisesRegex(
            ValidationError,
            "0부터 빠짐없이",
        ):
            LearningAssessmentAttemptResult.model_validate(payload)


class LearningAssessmentServiceTests(unittest.TestCase):
    def test_pair_must_match_stored_objective_order_and_depth(self):
        pair = LearningAssessmentPairDraft.model_validate(
            _valid_pair_payload()
        )

        validate_assessment_pair_against_objectives(
            pair,
            _stored_objectives(),
        )

        objectives = _stored_objectives()
        reordered_objectives = [
            objectives[0].model_copy(update={"sort_order": 2}),
            objectives[1].model_copy(update={"sort_order": 1}),
        ]
        with self.assertRaisesRegex(ValueError, "저장된 학습목표 계약"):
            validate_assessment_pair_against_objectives(
                pair,
                reordered_objectives,
            )

    @patch("services.learning_assessment_service.get_openai_model")
    @patch("services.learning_assessment_service.get_openai_client")
    def test_generation_uses_one_structured_call_without_database_ids(
        self,
        get_client,
        get_model,
    ):
        pair = LearningAssessmentPairDraft.model_validate(
            _valid_pair_payload()
        )
        fake_client = FakeOpenAIClient(pair)
        get_client.return_value = fake_client
        get_model.return_value = "test-model"

        generated = generate_learning_assessment_pair(
            course_name="Python",
            goal="조건문과 반복문을 설명하고 적용한다.",
            current_level=2,
            objectives=_stored_objectives(),
        )

        self.assertEqual(generated.pair, pair)
        self.assertEqual(len(fake_client.responses.calls), 1)
        request = fake_client.responses.calls[0]
        self.assertIs(request["text_format"], LearningAssessmentPairDraft)
        payload = json.loads(request["input"][1]["content"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("user_id", serialized)
        self.assertNotIn("plan_id", serialized)
        self.assertNotIn("contract_hash", serialized)

    def test_save_repository_sends_both_forms_to_one_rpc(self):
        pair = LearningAssessmentPairDraft.model_validate(
            _valid_pair_payload()
        )
        pair_key = "19eab587-84ed-4661-9e98-fc2b7e142de9"
        client = FakeRpcClient(
            {
                "user_id": "5441d349-a86d-4ed7-a67c-ae1048f1ad08",
                "plan_id": "3a3a5116-39bb-4747-a9ad-99f1c402c360",
                "pair_key": pair_key,
                "pre_assessment_id": "650ef473-7610-49bf-a769-2ea5c577026c",
                "post_assessment_id": "b92cf00c-b22a-449e-a50b-cda26881336d",
                "already_processed": False,
            }
        )

        result = save_learning_assessment_pair(
            supabase=client,
            user_id="5441d349-a86d-4ed7-a67c-ae1048f1ad08",
            plan_id="3a3a5116-39bb-4747-a9ad-99f1c402c360",
            pair_key=pair_key,
            generated=GeneratedLearningAssessmentPair(
                pair=pair,
                prompt_version="learning_assessment_v1",
                model_name="test-model",
            ),
        )

        self.assertFalse(result.already_processed)
        self.assertEqual(len(client.calls), 1)
        rpc_name, params = client.calls[0]
        self.assertEqual(rpc_name, "save_learning_assessment_pair")
        self.assertEqual(len(params["p_pre_questions"]), 6)
        self.assertEqual(len(params["p_post_questions"]), 6)


class LearningAssessmentRepositoryTests(unittest.TestCase):
    def test_state_repository_validates_owned_rpc_response(self):
        state_payload = {
            "user_id": "5441d349-a86d-4ed7-a67c-ae1048f1ad08",
            "plan_id": "3a3a5116-39bb-4747-a9ad-99f1c402c360",
            "today": "2026-09-05",
            "task_count": 6,
            "completed_task_count": 0,
            "has_learning_activity": False,
            "period_finished": False,
            "can_generate": False,
            "pre_eligible": True,
            "post_eligible": False,
            "pre_reason": None,
            "post_reason": "사전 진단을 먼저 완료해주세요.",
            "pre_assessment": _form_state_payload("pre"),
            "post_assessment": _form_state_payload("post")
            | {"questions": None},
            "pre_attempt": None,
            "post_attempt": None,
        }
        client = FakeRpcClient(state_payload)

        state = get_learning_assessment_state(
            supabase=client,
            user_id=state_payload["user_id"],
            plan_id=state_payload["plan_id"],
        )

        self.assertIsInstance(state, LearningAssessmentPlanState)
        self.assertTrue(state.pre_eligible)
        self.assertIsNone(state.post_assessment.questions)
        self.assertEqual(
            client.calls,
            [
                (
                    "get_learning_assessment_state",
                    {"p_plan_id": state_payload["plan_id"]},
                )
            ],
        )

    def test_state_rejects_answer_exposure_before_attempt(self):
        pre_form = _form_state_payload("pre")
        for index, question in enumerate(pre_form["questions"]):
            question["correct_answer_index"] = index % 4
            question["explanation"] = "아직 공개하면 안 되는 해설입니다."
        payload = {
            "user_id": "5441d349-a86d-4ed7-a67c-ae1048f1ad08",
            "plan_id": "3a3a5116-39bb-4747-a9ad-99f1c402c360",
            "today": "2026-09-05",
            "task_count": 6,
            "completed_task_count": 0,
            "has_learning_activity": False,
            "period_finished": False,
            "can_generate": False,
            "pre_eligible": True,
            "post_eligible": False,
            "pre_assessment": pre_form,
            "post_assessment": _form_state_payload("post")
            | {"questions": None},
            "pre_attempt": None,
            "post_attempt": None,
        }

        with self.assertRaisesRegex(ValidationError, "정답 공개 상태"):
            LearningAssessmentPlanState.model_validate(payload)

    def test_submission_repository_preserves_idempotency_key(self):
        payload = _attempt_payload()
        client = FakeRpcClient(payload)

        result = submit_learning_assessment_attempt(
            supabase=client,
            user_id="5441d349-a86d-4ed7-a67c-ae1048f1ad08",
            assessment_id=payload["assessment_id"],
            answers=[0, 0, 0, 1, 1, 1],
            submission_key=payload["submission_key"],
        )

        self.assertEqual(str(result.submission_key), payload["submission_key"])
        self.assertEqual(
            client.calls[0][1]["p_submission_key"],
            payload["submission_key"],
        )


class LearningAssessmentStateTests(unittest.TestCase):
    def test_navigation_selects_plan_once(self):
        state = {}

        request_learning_assessment_navigation(
            state,
            "3a3a5116-39bb-4747-a9ad-99f1c402c360",
        )

        self.assertEqual(state["learning_assessment_pending_navigation"], "학습 성과 리포트")
        self.assertEqual(
            consume_pending_assessment_plan(state),
            "3a3a5116-39bb-4747-a9ad-99f1c402c360",
        )
        self.assertIsNone(consume_pending_assessment_plan(state))

    def test_same_answers_reuse_submission_request_key(self):
        state = {}

        first_key = get_or_create_submission_request(
            state,
            assessment_id="9bd28f68-f30f-47f1-8dfc-8e8afe1082d5",
            answers=[0, 1, 2, 3, 0, 1],
        )
        retry_key = get_or_create_submission_request(
            state,
            assessment_id="9bd28f68-f30f-47f1-8dfc-8e8afe1082d5",
            answers=[0, 1, 2, 3, 0, 1],
        )
        changed_key = get_or_create_submission_request(
            state,
            assessment_id="9bd28f68-f30f-47f1-8dfc-8e8afe1082d5",
            answers=[1, 1, 2, 3, 0, 1],
        )

        self.assertEqual(first_key, retry_key)
        self.assertNotEqual(first_key, changed_key)

    def test_reset_removes_only_assessment_keys(self):
        state = {
            f"{LEARNING_ASSESSMENT_PREFIX}message": "완료",
            "weekly_review_plan_id": "keep",
        }

        clear_learning_assessment_state(state)

        self.assertEqual(state, {"weekly_review_plan_id": "keep"})


class LearningAssessmentMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).resolve().parents[1]
        cls.sql = (
            project_root / "supabase_learning_assessments.sql"
        ).read_text(encoding="utf-8")
        cls.manifest = (
            project_root / "supabase" / "migrations.toml"
        ).read_text(encoding="utf-8")

    def test_migration_uses_separate_rls_tables_and_composite_ownership(self):
        self.assertIn("create table public.learning_assessments", self.sql)
        self.assertIn(
            "create table public.learning_assessment_attempts",
            self.sql,
        )
        self.assertIn("learning_assessments_plan_owner_fk", self.sql)
        self.assertIn(
            "learning_assessment_attempts_assessment_owner_fk",
            self.sql,
        )
        self.assertGreaterEqual(
            self.sql.count("enable row level security"),
            2,
        )
        self.assertIn(
            "learning_assessments_question_count_range_check",
            self.sql,
        )
        self.assertIn(
            "learning_assessments_questions_length_check",
            self.sql,
        )

    def test_assessment_answers_are_accessed_only_through_owned_rpcs(self):
        self.assertIn(
            "revoke all on public.learning_assessments "
            "from public, anon, authenticated",
            self.sql,
        )
        self.assertIn("v_user_id uuid := auth.uid()", self.sql)
        self.assertIn("security definer", self.sql)
        self.assertIn("set search_path = ''", self.sql)
        self.assertIn("item.question - 'correct_answer_index'", self.sql)
        validation_sql = (
            Path(__file__).resolve().parents[1]
            / "supabase_learning_assessments_validation.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("config.value in ('search_path=', 'search_path=\"\"')", validation_sql)
        self.assertIn("procedure.oid = v_function_oid", validation_sql)

    def test_submission_is_official_once_idempotent_and_has_no_rewards(self):
        self.assertIn(
            "learning_assessment_attempts_official_unique",
            self.sql,
        )
        self.assertIn(
            "learning_assessment_attempts_submission_unique",
            self.sql,
        )
        self.assertIn("'already_processed', true", self.sql)
        self.assertNotIn("insert into public.exp_events", self.sql.lower())
        self.assertNotIn("update public.concept_mastery", self.sql.lower())

    def test_manifest_registers_migration_after_image_sources(self):
        self.assertIn('id = "040_learning_assessments"', self.manifest)
        self.assertIn(
            'depends_on = ["039_image_source_material"]',
            self.manifest,
        )


class LearningAssessmentIntegrationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).resolve().parents[1]
        cls.app_source = (project_root / "app.py").read_text(encoding="utf-8")
        cls.performance_source = (
            project_root / "views" / "learning_performance_view.py"
        ).read_text(encoding="utf-8")
        cls.create_plan_source = (
            project_root / "views" / "create_plan_view.py"
        ).read_text(encoding="utf-8")
        cls.completion_source = (
            project_root / "views" / "completion_feedback.py"
        ).read_text(encoding="utf-8")

    def test_performance_report_renders_assessment_as_first_tab(self):
        self.assertIn(
            '["학습 전·후 평가", "성과 요약", "학습목표별 성과", "성장 근거"]',
            self.performance_source,
        )
        self.assertIn(
            "render_learning_assessment_section(",
            self.performance_source,
        )

    def test_plan_save_and_completion_offer_assessment_navigation(self):
        self.assertIn("학습 전 진단 시작하기", self.create_plan_source)
        self.assertIn("사후 평가 확인하기", self.completion_source)
        self.assertIn(
            "request_learning_assessment_navigation",
            self.create_plan_source,
        )
        self.assertIn(
            "request_learning_assessment_navigation",
            self.completion_source,
        )

    def test_logout_and_navigation_include_assessment_state(self):
        self.assertIn("clear_learning_assessment_state", self.app_source)
        self.assertIn(
            "LEARNING_ASSESSMENT_PENDING_NAVIGATION_KEY",
            self.app_source,
        )

if __name__ == "__main__":
    unittest.main()
