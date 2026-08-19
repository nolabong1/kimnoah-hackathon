import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from models.coin_economy import (
    CoinTransaction,
    CoinTransactionType,
    CoinWallet,
)


USER_ID = UUID("11111111-1111-4111-8111-111111111111")
TRANSACTION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime.now(timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CoinEconomyModelTests(unittest.TestCase):
    def test_wallet_requires_matching_balance_and_totals(self):
        wallet = CoinWallet(
            user_id=USER_ID,
            balance=30,
            lifetime_earned=50,
            lifetime_spent=20,
            created_at=NOW,
            updated_at=NOW,
        )

        self.assertEqual(wallet.balance, 30)

        with self.assertRaises(ValidationError):
            CoinWallet(
                user_id=USER_ID,
                balance=31,
                lifetime_earned=50,
                lifetime_spent=20,
                created_at=NOW,
                updated_at=NOW,
            )

    def test_transaction_type_enforces_amount_direction(self):
        reward = CoinTransaction(
            id=TRANSACTION_ID,
            user_id=USER_ID,
            transaction_type=CoinTransactionType.TASK_COMPLETION,
            amount=5,
            balance_after=35,
            source_key="task:33333333-3333-4333-8333-333333333333",
            created_at=NOW,
        )

        self.assertEqual(reward.amount, 5)

        with self.assertRaises(ValidationError):
            CoinTransaction(
                id=TRANSACTION_ID,
                user_id=USER_ID,
                transaction_type=CoinTransactionType.PURCHASE,
                amount=30,
                balance_after=0,
                source_key="purchase:44444444-4444-4444-8444-444444444444",
                created_at=NOW,
            )

    def test_transaction_rejects_unsafe_source_key(self):
        with self.assertRaises(ValidationError):
            CoinTransaction(
                id=TRANSACTION_ID,
                user_id=USER_ID,
                transaction_type=CoinTransactionType.ONBOARDING,
                amount=30,
                balance_after=30,
                source_key="Onboarding Shop V1",
                created_at=NOW,
            )


class CoinEconomyMigrationTests(unittest.TestCase):
    def test_schema_contains_ownership_rls_and_idempotency(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_economy_schema.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("create table public.user_coin_wallets", migration)
        self.assertIn("create table public.coin_transactions", migration)
        self.assertIn("constraint user_coin_wallets_profile_fk", migration)
        self.assertIn("constraint coin_transactions_wallet_fk", migration)
        self.assertIn("unique (user_id, source_key)", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("using ((select auth.uid()) = user_id)", migration)
        self.assertIn("after insert on public.profiles", migration)
        self.assertIn("values (new.id, 30, 30, 0)", migration)
        self.assertNotIn("grant insert", migration.casefold())
        self.assertNotIn("grant update", migration.casefold())
        self.assertNotIn("grant delete", migration.casefold())

    def test_schema_uses_safe_internal_trigger_function(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_economy_schema.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("security definer", migration)
        self.assertIn("set search_path = ''", migration)
        self.assertIn(
            "revoke all on function public.initialize_coin_wallet_for_profile()",
            migration,
        )

    def test_validation_is_read_only_and_checks_ledger_totals(self):
        validation = (
            PROJECT_ROOT / "supabase_coin_economy_schema_validation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("set transaction read only", validation)
        self.assertIn("'shop_test_credit'", validation)
        self.assertIn("transaction.transaction_type = 'purchase'", validation)
        self.assertIn("'shop_test_purchase_refund'", validation)
        self.assertIn("rollback;", validation)

    def test_reward_trigger_uses_exp_ledger_and_approved_amounts(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_rewards.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("after insert on public.exp_events", migration)
        self.assertIn("when 'task_completion'", migration)
        self.assertIn("v_coin_amount := 5", migration)
        self.assertIn("when 'daily_completion'", migration)
        self.assertIn("when 'daily_challenge'", migration)
        self.assertIn("when 'weekly_challenge'", migration)
        self.assertIn("v_task_coins_awarded_today >= 25", migration)
        self.assertNotIn("when 'achievement'", migration)
        self.assertNotIn("when 'quiz_submission'", migration)

    def test_reward_trigger_is_internal_and_idempotent(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_rewards.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("security definer", migration)
        self.assertIn("set search_path = ''", migration)
        self.assertIn("on conflict (user_id, source_key) do nothing", migration)
        self.assertIn("from public, anon, authenticated", migration)

    def test_reward_validation_is_read_only_and_checks_daily_cap(self):
        validation = (
            PROJECT_ROOT / "supabase_coin_rewards_validation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("set transaction read only", validation)
        self.assertIn("having sum(transaction.amount) > 25", validation)
        self.assertIn("coin rewards validation: success", validation)
        self.assertIn("rollback;", validation)

    def test_test_reset_records_reversal_instead_of_deleting_coin_ledger(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_test_reset.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("before delete on public.exp_events", migration)
        self.assertIn("app.coin_test_reset", migration)
        self.assertIn(
            "reset_today_test_progress_without_coin_reversal",
            migration,
        )
        self.assertIn("'test_reset_reversal'", migration)
        self.assertIn("'reversal:' || v_reward_transaction.id::text", migration)
        self.assertIn("lifetime_earned = lifetime_earned + v_inserted_amount", migration)
        self.assertNotIn("delete from public.coin_transactions", migration)

    def test_test_reset_reversal_is_internal_and_idempotent(self):
        migration = (
            PROJECT_ROOT / "supabase_coin_test_reset.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("security definer", migration)
        self.assertIn("set search_path = ''", migration)
        self.assertIn("on conflict (user_id, source_key) do nothing", migration)
        self.assertIn("from public, anon, authenticated", migration)
        self.assertIn("v_wallet.balance < v_reward_transaction.amount", migration)
        self.assertIn(
            "grant execute on function public.reset_today_test_progress()",
            migration,
        )

    def test_test_reset_validation_checks_orphans_and_wallet_totals(self):
        validation = (
            PROJECT_ROOT / "supabase_coin_test_reset_validation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("set transaction read only", validation)
        self.assertIn("EXP 삭제 후 취소되지 않은 코인 보상 원장", validation)
        self.assertIn("wallet.lifetime_earned <> totals.earned", validation)
        self.assertIn("coin test reset validation: success", validation)
        self.assertIn("rollback;", validation)


if __name__ == "__main__":
    unittest.main()
