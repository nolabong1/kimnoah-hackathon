import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services.collection_service import build_collection_summary
from services.shop_catalog import SHOP_ITEM_CATALOG
from services.shop_repository import (
    get_shop_items,
    get_user_coin_wallet,
    get_user_inventory,
    get_user_study_room,
    purchase_shop_item,
    save_user_study_room,
)
from services.study_room_service import validate_study_room_equipment
from views.shop_view import load_shop_page_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-4000-8000-000000000001"
PURCHASE_ID = "00000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).isoformat()

STARTING_COINS = 30
TASK_REWARD = 5
DAILY_TASK_COIN_CAP = 25
DAILY_COMPLETION_REWARD = 10
DAILY_CHALLENGE_REWARD = 10
WEEKLY_CHALLENGE_REWARD = 30


class FakeResponse:
    def __init__(self, data):
        self.data = data


class StatefulRequest:
    def __init__(self, producer):
        self.producer = producer

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def order(self, _field, desc=False):
        del desc
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return FakeResponse(self.producer())


class InMemoryShopSupabase:
    """구매부터 컬렉션까지 repository 계약을 연결하는 테스트 대역입니다."""

    def __init__(self):
        self.wallet = {
            "user_id": USER_ID,
            "balance": STARTING_COINS,
            "lifetime_earned": STARTING_COINS,
            "lifetime_spent": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.items = [
            item.model_dump(mode="json")
            for item in SHOP_ITEM_CATALOG
        ]
        self.inventory = []
        self.room = None
        self.rpc_calls = []

    def table(self, table_name):
        producers = {
            "user_coin_wallets": lambda: dict(self.wallet),
            "shop_items": lambda: list(self.items),
            "user_inventory": lambda: list(self.inventory),
            "user_study_rooms": lambda: (
                None if self.room is None else dict(self.room)
            ),
        }
        return StatefulRequest(producers[table_name])

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, dict(params)))
        producers = {
            "purchase_shop_item": lambda: self._purchase(
                params["p_item_key"]
            ),
            "save_user_study_room": lambda: self._save_room(params),
        }
        return StatefulRequest(producers[function_name])

    def _purchase(self, item_key):
        existing = next(
            (
                entry
                for entry in self.inventory
                if entry["item_key"] == item_key
            ),
            None,
        )
        item = next(
            item for item in self.items
            if item["item_key"] == item_key
        )
        if existing is not None:
            return {
                "item_key": item_key,
                "price": item["price"],
                "coins_spent": 0,
                "balance": self.wallet["balance"],
                "already_owned": True,
                "purchase_transaction_id": existing[
                    "purchase_transaction_id"
                ],
                "acquired_at": existing["acquired_at"],
            }

        self.wallet["balance"] -= item["price"]
        self.wallet["lifetime_spent"] += item["price"]
        inventory_item = {
            "user_id": USER_ID,
            "item_key": item_key,
            "purchase_transaction_id": PURCHASE_ID,
            "price_paid": item["price"],
            "acquired_at": NOW,
        }
        self.inventory.append(inventory_item)
        return {
            "item_key": item_key,
            "price": item["price"],
            "coins_spent": item["price"],
            "balance": self.wallet["balance"],
            "already_owned": False,
            "purchase_transaction_id": PURCHASE_ID,
            "acquired_at": NOW,
        }

    def _save_room(self, params):
        equipment = {
            key.removeprefix("p_"): value
            for key, value in params.items()
        }
        normalized = validate_study_room_equipment(
            equipment,
            {entry["item_key"] for entry in self.inventory},
        )
        self.room = {
            "user_id": USER_ID,
            **normalized,
            "created_at": NOW,
            "updated_at": NOW,
        }
        return dict(self.room)


def _weekly_income(
    *,
    tasks_per_day: int,
    daily_completion_days: int,
    daily_challenges_per_day: int,
    weekly_challenges: int,
) -> int:
    task_income_per_day = min(
        tasks_per_day * TASK_REWARD,
        DAILY_TASK_COIN_CAP,
    )
    return (
        task_income_per_day * 7
        + daily_completion_days * DAILY_COMPLETION_REWARD
        + daily_challenges_per_day * 7 * DAILY_CHALLENGE_REWARD
        + weekly_challenges * WEEKLY_CHALLENGE_REWARD
    )


class ShopRoomFlowIntegrationTests(unittest.TestCase):
    def test_purchase_equip_and_collection_flow_preserves_idempotency(self):
        supabase = InMemoryShopSupabase()

        initial_data = load_shop_page_data(supabase, USER_ID)
        self.assertEqual(initial_data["wallet"]["balance"], 30)
        self.assertEqual(initial_data["inventory"], [])

        purchase = purchase_shop_item(supabase, "decor_green_plant")
        duplicate = purchase_shop_item(supabase, "decor_green_plant")
        self.assertEqual(purchase["coins_spent"], 30)
        self.assertTrue(duplicate["already_owned"])
        self.assertEqual(duplicate["coins_spent"], 0)
        self.assertEqual(get_user_coin_wallet(supabase, USER_ID)["balance"], 0)

        room = save_user_study_room(
            supabase,
            {"decor_left_item_key": "decor_green_plant"},
        )
        inventory = get_user_inventory(supabase, USER_ID)
        summary = build_collection_summary(
            get_shop_items(supabase),
            inventory,
            get_user_study_room(supabase, USER_ID),
        )

        self.assertEqual(room["decor_left_item_key"], "decor_green_plant")
        self.assertEqual(len(inventory), 1)
        self.assertEqual(summary.owned_count, 1)
        self.assertEqual(summary.equipped_count, 1)
        self.assertEqual(summary.completion_percent, 7)


class CoinEconomyBalanceTests(unittest.TestCase):
    def test_approved_catalog_meets_mvp_pacing_targets(self):
        total_price = sum(item.price for item in SHOP_ITEM_CATALOG)
        common_max = max(
            item.price
            for item in SHOP_ITEM_CATALOG
            if item.rarity.value == "common"
        )
        rare_max = max(
            item.price
            for item in SHOP_ITEM_CATALOG
            if item.rarity.value == "rare"
        )
        conservative_daily_income = (
            2 * TASK_REWARD + DAILY_COMPLETION_REWARD
        )
        engaged_daily_income = (
            3 * TASK_REWARD
            + DAILY_COMPLETION_REWARD
            + DAILY_CHALLENGE_REWARD
        )

        self.assertEqual(total_price, 1170)
        self.assertLessEqual(
            min(item.price for item in SHOP_ITEM_CATALOG),
            STARTING_COINS,
        )
        self.assertLessEqual(
            math.ceil(
                max(common_max - STARTING_COINS, 0)
                / conservative_daily_income
            ),
            3,
        )
        self.assertEqual(
            math.ceil(
                (rare_max - STARTING_COINS) / engaged_daily_income
            ),
            4,
        )
        self.assertEqual(
            math.ceil(
                (rare_max - STARTING_COINS) / conservative_daily_income
            ),
            7,
        )

    def test_full_collection_requires_multiple_weeks(self):
        remaining_price = (
            sum(item.price for item in SHOP_ITEM_CATALOG)
            - STARTING_COINS
        )
        conservative_income = _weekly_income(
            tasks_per_day=2,
            daily_completion_days=7,
            daily_challenges_per_day=0,
            weekly_challenges=0,
        )
        engaged_income = _weekly_income(
            tasks_per_day=3,
            daily_completion_days=7,
            daily_challenges_per_day=1,
            weekly_challenges=1,
        )
        maximum_income = _weekly_income(
            tasks_per_day=5,
            daily_completion_days=7,
            daily_challenges_per_day=3,
            weekly_challenges=2,
        )

        self.assertEqual(
            (conservative_income, engaged_income, maximum_income),
            (140, 275, 515),
        )
        self.assertEqual(
            (
                math.ceil(remaining_price / conservative_income),
                math.ceil(remaining_price / engaged_income),
                math.ceil(remaining_price / maximum_income),
            ),
            (9, 5, 3),
        )

    def test_sql_reward_values_match_balance_assumptions(self):
        reward_sql = (
            PROJECT_ROOT / "supabase_coin_rewards.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("v_coin_amount := 5", reward_sql)
        self.assertIn("v_coin_amount := 10", reward_sql)
        self.assertIn("v_coin_amount := 30", reward_sql)
        self.assertIn("v_task_coins_awarded_today >= 25", reward_sql)


class ShopRoomIntegrationValidationTests(unittest.TestCase):
    def test_consolidated_validation_is_read_only_and_checks_full_flow(self):
        validation = (
            PROJECT_ROOT / "supabase_shop_room_integration_validation.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("set transaction read only", validation)
        self.assertIn("exp_events_award_coins", validation)
        self.assertIn("purchase_shop_item", validation)
        self.assertIn("save_user_study_room", validation)
        self.assertIn("user_inventory", validation)
        self.assertIn("user_study_rooms", validation)
        self.assertIn("asia/seoul", validation)
        self.assertIn("shop room integration validation: success", validation)
        self.assertTrue(validation.rstrip().endswith("rollback;"))


if __name__ == "__main__":
    unittest.main()
