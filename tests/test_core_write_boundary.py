import unittest
from datetime import date
from pathlib import Path

from models.study_plan import (
    DailyStudyPlan,
    StudyTaskDraft,
    WeeklyStudyPlan,
)
from models.learning_blueprint import LearningEvidenceRequirement
from models.learning_objective import LearningObjectiveContract
from services.study_plan_repository import save_weekly_study_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, data):
        self.data = data
        self.rpc_calls = []

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, dict(params)))
        return FakeRequest(self.data)


def build_plan() -> WeeklyStudyPlan:
    objectives = [
        LearningObjectiveContract(
            objective_key="python_conditionals",
            title="조건문의 실행 흐름",
            description="조건식에 따라 실행 경로가 달라지는 원리를 적용합니다.",
            target_depth="foundation",
            evidence_requirements=[
                LearningEvidenceRequirement(
                    key="explain",
                    description="조건문의 실행 흐름을 설명할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="apply",
                    description="조건에 맞는 분기 코드를 작성할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="differentiate",
                    description="if와 elif의 역할을 구분할 수 있습니다.",
                ),
            ],
        ),
        LearningObjectiveContract(
            objective_key="python_loops",
            title="반복문의 실행과 적용",
            description="반복 조건과 실행 횟수를 설명하고 코드에 적용합니다.",
            target_depth="foundation",
            evidence_requirements=[
                LearningEvidenceRequirement(
                    key="explain",
                    description="반복문의 실행 순서를 설명할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="apply",
                    description="반복 코드를 작성할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="differentiate",
                    description="반복 조건의 차이를 구분할 수 있습니다.",
                ),
            ],
        ),
    ]
    return WeeklyStudyPlan(
        title="파이썬 7일 계획",
        course_name="파이썬",
        level_assessment="기초 문법을 적용할 수 있습니다.",
        weekly_goal="조건문과 반복문으로 작은 프로그램 완성",
        strategy="개념 학습 후 매일 짧은 실습을 진행합니다.",
        learning_objectives=objectives,
        days=[
            DailyStudyPlan(
                day_offset=day_offset,
                daily_focus=f"{day_offset + 1}일차 핵심 학습",
                tasks=[
                    StudyTaskDraft(
                        objective_key=(
                            "python_conditionals"
                            if day_offset < 3
                            else "python_loops"
                        ),
                        title=f"{day_offset + 1}일차 실습",
                        description="예제를 실행하고 결과를 설명합니다.",
                        task_type=("quiz" if day_offset == 6 else "learn"),
                        estimated_minutes=30,
                    )
                ],
            )
            for day_offset in range(7)
        ],
        motivation_message="작은 실습을 꾸준히 이어가세요.",
    )


class StudyPlanWriteBoundaryRepositoryTests(unittest.TestCase):
    def test_plan_and_tasks_are_sent_to_single_server_rpc(self):
        supabase = FakeSupabase(
            {
                "id": PLAN_ID,
                "user_id": USER_ID,
                "title": "파이썬 7일 계획",
                "learning_objective_count": 2,
            }
        )
        schedule = {f"{offset}일차": 60 for offset in range(7)}

        saved = save_weekly_study_plan(
            supabase=supabase,
            user_id=USER_ID,
            plan=build_plan(),
            course_name="파이썬",
            goal="조건문과 반복문 익히기",
            current_level=3,
            start_date=date(2026, 8, 24),
            available_schedule=schedule,
        )

        self.assertEqual(saved["id"], PLAN_ID)
        self.assertEqual(len(supabase.rpc_calls), 1)
        function_name, payload = supabase.rpc_calls[0]
        self.assertEqual(function_name, "save_weekly_study_plan_with_tasks")
        self.assertEqual(payload["p_available_schedule"], schedule)
        self.assertEqual(len(payload["p_weekly_overview"]), 7)
        self.assertEqual(len(payload["p_learning_objectives"]), 2)
        self.assertEqual(len(payload["p_tasks"]), 7)
        self.assertEqual(
            {task["day_offset"] for task in payload["p_tasks"]},
            set(range(7)),
        )
        self.assertTrue(
            all(
                "user_id" not in task
                and "plan_id" not in task
                and "status" not in task
                for task in payload["p_tasks"]
            )
        )
        self.assertTrue(
            all(
                len(objective["contract_hash"]) == 64
                for objective in payload["p_learning_objectives"]
            )
        )
        self.assertEqual(
            {task["objective_key"] for task in payload["p_tasks"]},
            {"python_conditionals", "python_loops"},
        )

    def test_plan_save_rejects_wrong_owner_response(self):
        supabase = FakeSupabase(
            {
                "id": PLAN_ID,
                "user_id": "33333333-3333-4333-8333-333333333333",
            }
        )

        with self.assertRaises(RuntimeError):
            save_weekly_study_plan(
                supabase=supabase,
                user_id=USER_ID,
                plan=build_plan(),
                course_name="파이썬",
                goal="조건문과 반복문 익히기",
                current_level=3,
                start_date=date(2026, 8, 24),
                available_schedule={
                    f"{offset}일차": 60 for offset in range(7)
                },
            )


class CoreWriteBoundaryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = (
            PROJECT_ROOT / "supabase_core_write_boundary.sql"
        ).read_text(encoding="utf-8").casefold()
        self.validation = (
            PROJECT_ROOT / "supabase_core_write_boundary_validation.sql"
        ).read_text(encoding="utf-8").casefold()

    def test_plan_rpc_owns_identity_status_and_dates(self):
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("v_user_id uuid := auth.uid()", self.migration)
        self.assertIn("p_start_date + 6", self.migration)
        self.assertIn("'active'", self.migration)
        self.assertIn("'pending'", self.migration)

    def test_direct_core_table_writes_are_revoked(self):
        self.assertIn(
            "revoke insert, update on public.study_plans from authenticated",
            self.migration,
        )
        self.assertIn(
            "revoke insert, update, delete on public.study_tasks from authenticated",
            self.migration,
        )
        self.assertIn(
            "revoke insert, update, delete on public.quizzes from authenticated",
            self.migration,
        )

    def test_validation_is_read_only_and_checks_both_save_rpcs(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("save_weekly_study_plan_with_tasks", self.validation)
        self.assertIn("save_quiz_with_concepts", self.validation)
        self.assertIn("core write boundary validation: success", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
