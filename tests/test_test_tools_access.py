import unittest
from pathlib import Path

from services.test_tools_repository import can_use_test_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


class TestToolsAccessRepositoryTests(unittest.TestCase):
    def test_reads_server_authorization_result(self):
        supabase = FakeSupabase(True)

        self.assertTrue(can_use_test_tools(supabase))
        self.assertEqual(
            supabase.rpc_calls,
            [("can_use_test_tools", {})],
        )

    def test_rejects_non_boolean_response(self):
        with self.assertRaises(RuntimeError):
            can_use_test_tools(FakeSupabase({"allowed": True}))


class TestToolsAccessMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = (
            PROJECT_ROOT / "supabase_test_tool_access.sql"
        ).read_text(encoding="utf-8").casefold()
        self.validation = (
            PROJECT_ROOT / "supabase_test_tool_access_validation.sql"
        ).read_text(encoding="utf-8").casefold()

    def test_access_table_is_server_only_and_rls_enabled(self):
        self.assertIn(
            "create table if not exists public.test_tool_access",
            self.migration,
        )
        self.assertIn("enable row level security", self.migration)
        self.assertIn(
            "revoke all on public.test_tool_access from public, anon, authenticated",
            self.migration,
        )
        self.assertNotIn(
            "grant select on public.test_tool_access",
            self.migration,
        )

    def test_public_test_rpcs_require_server_access_check(self):
        self.assertEqual(
            self.migration.count("perform public.require_test_tool_access();"),
            4,
        )
        self.assertIn("reset_today_test_progress_unchecked", self.migration)
        self.assertIn(
            "complete_study_plan_for_weekly_review_test_unchecked",
            self.migration,
        )
        self.assertIn("start_shop_test_session_unchecked", self.migration)
        self.assertIn("reset_shop_test_session_unchecked", self.migration)

    def test_validation_is_read_only_and_checks_internal_permissions(self):
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("has_function_privilege", self.validation)
        self.assertIn("require_test_tool_access", self.validation)
        self.assertIn("test tool access validation: success", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
