import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from views.shop_state import clear_shop_state
from views.shop_view import execute_shop_purchase, filter_shop_items


USER_ID = "00000000-0000-4000-8000-000000000001"
TRANSACTION_ID = "00000000-0000-4000-8000-000000000002"
NOW = datetime.now(timezone.utc).isoformat()


def _shop_item(
    item_key: str,
    name_ko: str,
    category: str,
    allowed_slots: list[str],
    rarity: str,
    price: int,
    layer: int,
    sort_order: int,
) -> dict:
    asset_folder = {
        "background": "backgrounds",
        "floor": "floors",
        "desk": "desks",
        "chair": "chairs",
        "decoration": "decorations",
        "accent": "accents",
    }[category]
    return {
        "item_key": item_key,
        "name_ko": name_ko,
        "category": category,
        "allowed_slots": allowed_slots,
        "rarity": rarity,
        "price": price,
        "layer": layer,
        "overlay_path": (
            f"assets/study_room/items/{asset_folder}/{item_key}.png"
        ),
        "thumbnail_path": f"assets/study_room/thumbnails/{item_key}.webp",
        "sort_order": sort_order,
        "is_active": True,
    }


ITEMS = [
    _shop_item(
        "decor_green_plant",
        "작은 초록 식물",
        "decoration",
        ["decor_left", "decor_right"],
        "common",
        30,
        50,
        120,
    ),
    _shop_item(
        "desk_oak_basic",
        "원목 학습 책상",
        "desk",
        ["desk"],
        "common",
        60,
        30,
        70,
    ),
]


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data

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
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, *, inventory=None):
        self.inventory = inventory or []
        self.rpc_calls = []

    def table(self, table_name):
        data_by_table = {
            "shop_items": ITEMS,
            "user_coin_wallets": {
                "user_id": USER_ID,
                "balance": 50,
                "lifetime_earned": 80,
                "lifetime_spent": 30,
                "created_at": NOW,
                "updated_at": NOW,
            },
            "user_inventory": self.inventory,
        }
        return FakeRequest(data_by_table[table_name])

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        return FakeRequest(
            {
                "item_key": params["p_item_key"],
                "price": 30,
                "coins_spent": 30,
                "balance": 20,
                "already_owned": False,
                "purchase_transaction_id": TRANSACTION_ID,
                "acquired_at": NOW,
            }
        )


def render_shop_test_page(supabase, user_id):
    from views.shop_view import load_shop_page_data, render_shop_market

    shop_data = load_shop_page_data(supabase, user_id)
    render_shop_market(supabase, shop_data)


def render_inventory_test_page(supabase, user_id):
    from views.shop_view import load_shop_page_data, render_shop_inventory

    shop_data = load_shop_page_data(supabase, user_id)
    render_shop_inventory(shop_data)


class ShopViewPureLogicTests(unittest.TestCase):
    def test_category_filter_preserves_catalog_order(self):
        self.assertEqual(filter_shop_items(ITEMS, "전체"), ITEMS)
        self.assertEqual(
            [item["item_key"] for item in filter_shop_items(ITEMS, "책상")],
            ["desk_oak_basic"],
        )
        self.assertEqual(filter_shop_items(ITEMS, "알 수 없음"), [])

    def test_shop_reset_removes_only_shop_prefixed_state(self):
        state = {
            "shop_success_message": "완료",
            "shop_category_filter": "책상",
            "gamification_success_message": "보존",
            "auth_user": SimpleNamespace(id=USER_ID),
        }

        clear_shop_state(state)

        self.assertNotIn("shop_success_message", state)
        self.assertNotIn("shop_category_filter", state)
        self.assertIn("gamification_success_message", state)
        self.assertIn("auth_user", state)


class ShopViewInteractionTests(unittest.TestCase):
    def test_market_renders_wallet_and_disables_unaffordable_item(self):
        supabase = FakeSupabase()

        app = AppTest.from_function(
            render_shop_test_page,
            args=(supabase, USER_ID),
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["보유 코인", "누적 획득", "누적 사용"],
        )
        buy_buttons = [
            button
            for button in app.button
            if button.label == "구매하기"
        ]
        self.assertEqual(len(buy_buttons), 2)
        self.assertFalse(buy_buttons[0].disabled)
        self.assertTrue(buy_buttons[1].disabled)
        self.assertEqual(supabase.rpc_calls, [])

    def test_purchase_requires_confirmation_before_rpc(self):
        supabase = FakeSupabase()
        app = AppTest.from_function(
            render_shop_test_page,
            args=(supabase, USER_ID),
        ).run()

        buy_button = next(
            button
            for button in app.button
            if button.label == "구매하기" and not button.disabled
        )
        app = buy_button.click().run()

        self.assertEqual(supabase.rpc_calls, [])
        confirm_button = next(
            button
            for button in app.button
            if button.label == "구매 확정"
        )
        self.assertFalse(confirm_button.disabled)
        self.assertEqual(supabase.rpc_calls, [])

    def test_confirmed_purchase_calls_rpc_once_and_builds_message(self):
        supabase = FakeSupabase()

        message = execute_shop_purchase(supabase, ITEMS[0])

        self.assertEqual(
            supabase.rpc_calls,
            [
                (
                    "purchase_shop_item",
                    {"p_item_key": "decor_green_plant"},
                )
            ],
        )
        self.assertEqual(
            message,
            "'작은 초록 식물' 구매를 완료했습니다. 남은 코인은 20개입니다.",
        )

    def test_inventory_displays_owned_item_without_purchase_action(self):
        inventory = [
            {
                "user_id": USER_ID,
                "item_key": "decor_green_plant",
                "purchase_transaction_id": TRANSACTION_ID,
                "price_paid": 30,
                "acquired_at": NOW,
            }
        ]
        supabase = FakeSupabase(inventory=inventory)

        app = AppTest.from_function(
            render_inventory_test_page,
            args=(supabase, USER_ID),
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertTrue(
            any(
                "작은 초록 식물" in item.value
                for item in app.markdown
            )
        )
        self.assertEqual(
            [button.label for button in app.button],
            [],
        )


if __name__ == "__main__":
    unittest.main()
