import unittest
from unittest.mock import patch

from services.shop_catalog import SHOP_ITEMS_BY_KEY
from views import shop_purchase_reveal_component
from views.shop_purchase_reveal_component import (
    build_shop_purchase_feedback,
)
from views.shop_view import execute_shop_purchase_feedback
from views.shop_state import pop_purchase_reveal, queue_purchase_reveal


def _item() -> dict:
    return SHOP_ITEMS_BY_KEY["decor_green_plant"].model_dump(mode="json")


def _result(*, already_owned: bool = False) -> dict:
    return {
        "item_key": "decor_green_plant",
        "price": 30,
        "coins_spent": 0 if already_owned else 30,
        "balance": 120,
        "already_owned": already_owned,
    }


class ShopPurchaseRevealTests(unittest.TestCase):
    def test_new_purchase_builds_reveal_with_approved_thumbnail(self):
        feedback = build_shop_purchase_feedback(_item(), _result())

        self.assertTrue(feedback["newly_purchased"])
        self.assertEqual(feedback["item_name"], "작은 초록 식물")
        self.assertEqual(feedback["coins_spent"], 30)
        self.assertTrue(feedback["thumbnail"].startswith("data:image/webp;base64,"))

    def test_duplicate_purchase_does_not_queue_reveal(self):
        state = {}
        feedback = build_shop_purchase_feedback(
            _item(),
            _result(already_owned=True),
        )

        queue_purchase_reveal(state, feedback)

        self.assertFalse(feedback["newly_purchased"])
        self.assertEqual(pop_purchase_reveal(state), None)

    def test_reveal_is_consumed_exactly_once(self):
        state = {}
        feedback = build_shop_purchase_feedback(_item(), _result())

        queue_purchase_reveal(state, feedback)

        self.assertEqual(pop_purchase_reveal(state), feedback)
        self.assertIsNone(pop_purchase_reveal(state))

    def test_catalog_and_purchase_result_must_match(self):
        result = _result()
        result["item_key"] = "desk_oak_basic"

        with self.assertRaisesRegex(RuntimeError, "요청과 일치"):
            build_shop_purchase_feedback(_item(), result)

    def test_purchase_feedback_calls_purchase_rpc_once(self):
        supabase = object()

        with patch(
            "views.shop_view.purchase_shop_item",
            return_value=_result(),
        ) as purchase:
            feedback = execute_shop_purchase_feedback(supabase, _item())

        purchase.assert_called_once_with(supabase, "decor_green_plant")
        self.assertTrue(feedback["newly_purchased"])

    def test_reveal_component_does_not_emit_purchase_events(self):
        source = shop_purchase_reveal_component._PURCHASE_REVEAL_JS

        self.assertNotIn("setStateValue", source)
        self.assertNotIn("setTriggerValue", source)
        self.assertNotIn("Streamlit.setComponentValue", source)
        self.assertNotIn("window.parent.postMessage", source)


if __name__ == "__main__":
    unittest.main()
