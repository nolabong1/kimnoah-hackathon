import unittest
from copy import deepcopy
from pathlib import Path

from services.dashboard_repository import get_dashboard_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "99999999-9999-4999-8999-999999999999"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
TASK_ID = "33333333-3333-4333-8333-333333333333"


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeRpcRequest:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, data):
        self.data = data
        self.rpc_calls = []
        self.table_calls = []

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, deepcopy(params)))
        return FakeRpcRequest(self.data)

    def table(self, table_name):
        self.table_calls.append(table_name)
        raise AssertionError("대시보드 스냅샷은 개별 테이블을 조회하면 안 됩니다.")


def build_snapshot(*, user_id=USER_ID):
    return {
        "user_id": user_id,
        "plan_id": PLAN_ID,
        "plan_tasks": [
            {
                "id": TASK_ID,
                "scheduled_date": "2026-08-26",
                "title": "반복문 핵심 익히기",
                "description": "for문의 동작을 정리합니다.",
                "task_type": "learn",
                "estimated_minutes": 30,
                "status": "pending",
                "source_type": "weekly_plan",
                "concept_id": None,
                "review_stage": None,
                "review_interval_days": None,
            }
        ],
        "concept_masteries": [],
        "achievements": [],
        "challenges": [],
        "badge_showcase": [],
    }


class DashboardSnapshotRepositoryTests(unittest.TestCase):
    def test_dashboard_data_uses_one_owned_snapshot_rpc(self):
        supabase = FakeSupabase(build_snapshot())

        result = get_dashboard_snapshot(
            supabase=supabase,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            course_key="python",
        )

        self.assertEqual(result["plan_id"], PLAN_ID)
        self.assertEqual(result["plan_tasks"][0]["id"], TASK_ID)
        self.assertEqual(supabase.table_calls, [])
        self.assertEqual(
            supabase.rpc_calls,
            [
                (
                    "get_dashboard_snapshot",
                    {
                        "p_plan_id": PLAN_ID,
                        "p_course_key": "python",
                    },
                )
            ],
        )

    def test_dashboard_snapshot_rejects_wrong_owner(self):
        supabase = FakeSupabase(build_snapshot(user_id=OTHER_USER_ID))

        with self.assertRaisesRegex(RuntimeError, "사용자 소유권"):
            get_dashboard_snapshot(
                supabase=supabase,
                user_id=USER_ID,
                plan_id=PLAN_ID,
                course_key="python",
            )

    def test_invalid_inputs_do_not_call_database(self):
        supabase = FakeSupabase(build_snapshot())

        with self.assertRaises(ValueError):
            get_dashboard_snapshot(
                supabase=supabase,
                user_id=USER_ID,
                plan_id="not-a-uuid",
                course_key="python",
            )

        self.assertEqual(supabase.rpc_calls, [])


class DashboardSnapshotMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = (
            PROJECT_ROOT / "supabase_dashboard_snapshot.sql"
        ).read_text(encoding="utf-8").casefold()
        self.validation = (
            PROJECT_ROOT / "supabase_dashboard_snapshot_validation.sql"
        ).read_text(encoding="utf-8").casefold()

    def test_rpc_is_read_only_owned_and_restricted(self):
        self.assertIn("stable", self.migration)
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertIn("v_user_id uuid := auth.uid()", self.migration)
        self.assertIn("plan.user_id = v_user_id", self.migration)
        self.assertNotIn("insert into", self.migration)
        self.assertNotIn("update public", self.migration)
        self.assertNotIn("delete from", self.migration)
        self.assertIn(
            "grant execute on function public.get_dashboard_snapshot(uuid, text)\n"
            "to authenticated",
            self.migration,
        )

    def test_validation_is_read_only_and_checks_permissions(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("has_function_privilege", self.validation)
        self.assertIn("authenticated", self.validation)
        self.assertIn("anon", self.validation)
        self.assertIn("dashboard snapshot validation: success", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
