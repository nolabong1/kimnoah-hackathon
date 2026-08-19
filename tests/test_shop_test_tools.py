import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from models.coin_economy import CoinTransaction, CoinTransactionType
from models.shop import ShopTestResetResult
from services.shop_repository import (
    get_active_shop_test_session,
    reset_shop_test_session,
    start_shop_test_session,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
TRANSACTION_ID = "33333333-3333-4333-8333-333333333333"
NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc).isoformat()


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data
        self.filters = {}
        self.selected = None
        self.single_requested = False

    def select(self, fields):
        self.selected = fields
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def maybe_single(self):
        self.single_requested = True
        return self

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, *, table_result=None, rpc_results=None):
        self.table_result = table_result
        self.rpc_results = rpc_results or {}
        self.table_requests = {}
        self.rpc_calls = []

    def table(self, table_name):
        request = FakeRequest(self.table_result)
        self.table_requests[table_name] = request
        return request

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, dict(params)))
        return FakeRequest(self.rpc_results[function_name])


def _active_session_row():
    return {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "status": "active",
        "credit_amount": 1200,
        "credit_transaction_id": TRANSACTION_ID,
        "inventory_snapshot": ["decor_green_plant"],
        "room_snapshot": {"decor_left_item_key": "decor_green_plant"},
        "refunded_purchase_count": 0,
        "refunded_coin_amount": 0,
        "removed_inventory_count": 0,
        "balance_after_reset": None,
        "started_at": NOW,
        "reset_at": None,
    }


class ShopTestToolModelTests(unittest.TestCase):
    def test_new_coin_transaction_types_enforce_direction(self):
        credit = CoinTransaction(
            id=TRANSACTION_ID,
            user_id=USER_ID,
            transaction_type=CoinTransactionType.SHOP_TEST_CREDIT,
            amount=1200,
            balance_after=1230,
            source_key=f"shop_test:{SESSION_ID}:credit",
            related_entity_id=SESSION_ID,
            created_at=NOW,
        )
        refund = CoinTransaction(
            id="44444444-4444-4444-8444-444444444444",
            user_id=USER_ID,
            transaction_type=CoinTransactionType.SHOP_TEST_PURCHASE_REFUND,
            amount=30,
            balance_after=1230,
            source_key=f"shop_test:{SESSION_ID}:purchase_refund",
            related_entity_id=SESSION_ID,
            created_at=NOW,
        )

        self.assertEqual(credit.amount, 1200)
        self.assertEqual(refund.amount, 30)

        with self.assertRaises(ValidationError):
            CoinTransaction(
                id=TRANSACTION_ID,
                user_id=USER_ID,
                transaction_type=CoinTransactionType.SHOP_TEST_CREDIT,
                amount=-1200,
                balance_after=30,
                source_key=f"shop_test:{SESSION_ID}:invalid",
                created_at=NOW,
            )

    def test_reset_result_requires_matching_purchase_and_removal_counts(self):
        with self.assertRaises(ValidationError):
            ShopTestResetResult(
                session_id=SESSION_ID,
                refunded_purchase_count=2,
                refunded_coin_amount=70,
                removed_inventory_count=1,
                balance=30,
                already_reset=False,
                reset_at=NOW,
            )


class ShopTestToolRepositoryTests(unittest.TestCase):
    def test_active_session_read_filters_owner_and_status(self):
        supabase = FakeSupabase(table_result=_active_session_row())

        result = get_active_shop_test_session(supabase, USER_ID)

        self.assertEqual(result["id"], SESSION_ID)
        request = supabase.table_requests["shop_test_sessions"]
        self.assertEqual(
            request.filters,
            {"user_id": USER_ID, "status": "active"},
        )
        self.assertTrue(request.single_requested)

    def test_missing_active_session_returns_none(self):
        supabase = FakeSupabase(table_result=None)

        self.assertIsNone(get_active_shop_test_session(supabase, USER_ID))

    def test_start_and_reset_use_server_rpc(self):
        start_result = {
            "session_id": SESSION_ID,
            "credit_amount": 1200,
            "balance": 1230,
            "already_active": False,
            "started_at": NOW,
        }
        reset_result = {
            "session_id": SESSION_ID,
            "refunded_purchase_count": 2,
            "refunded_coin_amount": 70,
            "removed_inventory_count": 2,
            "balance": 30,
            "already_reset": False,
            "reset_at": NOW,
        }
        supabase = FakeSupabase(
            rpc_results={
                "start_shop_test_session": start_result,
                "reset_shop_test_session": reset_result,
            }
        )

        started = start_shop_test_session(supabase)
        reset = reset_shop_test_session(supabase, SESSION_ID)

        self.assertEqual(started["credit_amount"], 1200)
        self.assertEqual(reset["refunded_coin_amount"], 70)
        self.assertEqual(
            supabase.rpc_calls,
            [
                ("start_shop_test_session", {}),
                (
                    "reset_shop_test_session",
                    {"p_session_id": SESSION_ID},
                ),
            ],
        )


class ShopTestToolMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migration = (
            PROJECT_ROOT / "supabase_shop_test_tools.sql"
        ).read_text(encoding="utf-8").casefold()
        self.validation = (
            PROJECT_ROOT / "supabase_shop_test_tools_validation.sql"
        ).read_text(encoding="utf-8").casefold()

    def test_migration_uses_owned_session_and_server_only_writes(self):
        self.assertIn("create table public.shop_test_sessions", self.migration)
        self.assertIn("enable row level security", self.migration)
        self.assertIn("auth.uid()", self.migration)
        self.assertIn("security definer", self.migration)
        self.assertIn("set search_path = ''", self.migration)
        self.assertNotIn(
            "grant insert on public.shop_test_sessions",
            self.migration,
        )
        self.assertNotIn(
            "grant update on public.shop_test_sessions",
            self.migration,
        )

    def test_migration_snapshots_tags_and_restores_shop_state(self):
        self.assertIn("inventory_snapshot", self.migration)
        self.assertIn("room_snapshot", self.migration)
        self.assertIn("item_transforms", self.migration)
        self.assertIn("'shop_test_credit'", self.migration)
        self.assertIn("'shop_test_purchase_refund'", self.migration)
        self.assertIn("v_test_session_id", self.migration)
        self.assertIn("delete from public.user_inventory", self.migration)
        self.assertIn("insert into public.user_study_rooms", self.migration)

    def test_rpc_permissions_and_validation_are_read_only(self):
        self.assertIn(
            "grant execute on function public.start_shop_test_session()",
            self.migration,
        )
        self.assertIn(
            "grant execute on function public.reset_shop_test_session(uuid)",
            self.migration,
        )
        self.assertIn("set transaction read only", self.validation)
        self.assertIn("shop test tools validation: success", self.validation)
        self.assertTrue(self.validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
