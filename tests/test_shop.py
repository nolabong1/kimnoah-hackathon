import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from models.shop import ShopItem, ShopItemCategory, ShopItemRarity, StudyRoomSlot
from services.shop_catalog import SHOP_ITEM_CATALOG, SHOP_ITEMS_BY_KEY
from services.shop_repository import (
    get_shop_items,
    get_user_coin_wallet,
    get_user_inventory,
    purchase_shop_item,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-4000-8000-000000000001"
TRANSACTION_ID = "00000000-0000-4000-8000-000000000002"
NOW = datetime.now(timezone.utc).isoformat()


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data
        self.selected = None
        self.filters = {}
        self.orders = []
        self.single_requested = False

    def select(self, fields):
        self.selected = fields
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def order(self, field, desc=False):
        self.orders.append((field, desc))
        return self

    def maybe_single(self):
        self.single_requested = True
        return self

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, *, rpc_results=None, table_results=None):
        self.rpc_results = rpc_results or {}
        self.table_results = table_results or {}
        self.rpc_calls = []
        self.table_requests = {}

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        return FakeRequest(self.rpc_results[function_name])

    def table(self, table_name):
        request = FakeRequest(self.table_results.get(table_name, []))
        self.table_requests[table_name] = request
        return request


class ShopCatalogTests(unittest.TestCase):
    def test_catalog_contains_approved_unique_items_and_prices(self):
        self.assertEqual(len(SHOP_ITEM_CATALOG), 15)
        self.assertEqual(len(SHOP_ITEMS_BY_KEY), 15)
        self.assertEqual(sum(item.price for item in SHOP_ITEM_CATALOG), 1170)
        self.assertEqual(
            len({item.sort_order for item in SHOP_ITEM_CATALOG}),
            15,
        )
        self.assertEqual(SHOP_ITEMS_BY_KEY["decor_green_plant"].price, 30)
        self.assertEqual(SHOP_ITEMS_BY_KEY["desk_neon_coder"].price, 170)

    def test_item_model_rejects_category_slot_mismatch(self):
        with self.assertRaises(ValidationError):
            ShopItem(
                item_key="invalid_desk",
                name_ko="잘못된 책상",
                category=ShopItemCategory.DESK,
                allowed_slots=(StudyRoomSlot.FLOOR,),
                rarity=ShopItemRarity.COMMON,
                price=30,
                layer=30,
                overlay_path="assets/item.png",
                thumbnail_path="assets/item.webp",
                sort_order=999,
            )

    def test_python_catalog_values_exist_in_sql_seed(self):
        migration = (
            PROJECT_ROOT / "supabase_shop_inventory.sql"
        ).read_text(encoding="utf-8")

        for item in SHOP_ITEM_CATALOG:
            self.assertIn(f"'{item.item_key}'", migration)
            self.assertIn(f"'{item.overlay_path}'", migration)
            self.assertIn(f"'{item.thumbnail_path}'", migration)


class ShopRepositoryTests(unittest.TestCase):
    def test_owned_reads_filter_user_id(self):
        wallet_row = {
            "user_id": USER_ID,
            "balance": 30,
            "lifetime_earned": 30,
            "lifetime_spent": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        inventory_row = {
            "user_id": USER_ID,
            "item_key": "decor_green_plant",
            "purchase_transaction_id": TRANSACTION_ID,
            "price_paid": 30,
            "acquired_at": NOW,
        }
        supabase = FakeSupabase(
            table_results={
                "user_coin_wallets": wallet_row,
                "user_inventory": [inventory_row],
            }
        )

        wallet = get_user_coin_wallet(supabase, USER_ID)
        inventory = get_user_inventory(supabase, USER_ID)

        self.assertEqual(wallet["balance"], 30)
        self.assertEqual(inventory[0]["item_key"], "decor_green_plant")
        self.assertEqual(
            supabase.table_requests["user_coin_wallets"].filters["user_id"],
            USER_ID,
        )
        self.assertEqual(
            supabase.table_requests["user_inventory"].filters["user_id"],
            USER_ID,
        )

    def test_catalog_read_filters_active_and_orders_on_server(self):
        supabase = FakeSupabase(table_results={"shop_items": []})

        self.assertEqual(get_shop_items(supabase), [])

        request = supabase.table_requests["shop_items"]
        self.assertEqual(request.filters["is_active"], True)
        self.assertEqual(request.orders, [("sort_order", False)])

    def test_purchase_sends_only_item_key_and_validates_result(self):
        response = {
            "item_key": "decor_green_plant",
            "price": 30,
            "coins_spent": 30,
            "balance": 0,
            "already_owned": False,
            "purchase_transaction_id": TRANSACTION_ID,
            "acquired_at": NOW,
        }
        supabase = FakeSupabase(
            rpc_results={"purchase_shop_item": response}
        )

        result = purchase_shop_item(supabase, " decor_green_plant ")

        self.assertEqual(result["balance"], 0)
        self.assertEqual(
            supabase.rpc_calls,
            [
                (
                    "purchase_shop_item",
                    {"p_item_key": "decor_green_plant"},
                )
            ],
        )

    def test_duplicate_purchase_must_spend_zero_coins(self):
        duplicate_response = {
            "item_key": "decor_green_plant",
            "price": 30,
            "coins_spent": 30,
            "balance": 0,
            "already_owned": True,
            "purchase_transaction_id": TRANSACTION_ID,
            "acquired_at": NOW,
        }
        supabase = FakeSupabase(
            rpc_results={"purchase_shop_item": duplicate_response}
        )

        with self.assertRaises(RuntimeError):
            purchase_shop_item(supabase, "decor_green_plant")

    def test_unknown_item_is_rejected_before_rpc(self):
        supabase = FakeSupabase()

        with self.assertRaises(ValueError):
            purchase_shop_item(supabase, "unknown_item")

        self.assertEqual(supabase.rpc_calls, [])


class ShopMigrationTests(unittest.TestCase):
    def test_schema_uses_server_price_and_atomic_purchase_ledger(self):
        migration = (
            PROJECT_ROOT / "supabase_shop_inventory.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("create table public.shop_items", migration)
        self.assertIn("create table public.user_inventory", migration)
        self.assertIn("price_paid integer not null", migration)
        self.assertIn("v_wallet.balance < v_item.price", migration)
        self.assertIn("'purchase:' || v_item.item_key", migration)
        self.assertIn("for update", migration)
        self.assertNotIn("p_price", migration)

    def test_schema_protects_inventory_and_purchase_ownership(self):
        migration = (
            PROJECT_ROOT / "supabase_shop_inventory.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("user_inventory_purchase_owner_fk", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("using ((select auth.uid()) = user_id)", migration)
        self.assertNotIn("grant insert on public.user_inventory", migration)
        self.assertNotIn("grant update on public.user_inventory", migration)

    def test_validation_checks_catalog_and_purchase_consistency(self):
        validation = (
            PROJECT_ROOT / "supabase_shop_inventory_validation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("set transaction read only", validation)
        self.assertIn("<> 15", validation)
        self.assertIn("<> 1170", validation)
        self.assertIn("인벤토리와 구매 코인 원장이 일치", validation)
        self.assertIn("shop inventory validation: success", validation)
        self.assertIn("rollback;", validation)


if __name__ == "__main__":
    unittest.main()
