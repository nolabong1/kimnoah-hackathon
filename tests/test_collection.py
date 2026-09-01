import unittest

from streamlit.testing.v1 import AppTest

from services.collection_service import build_collection_summary
from services.shop_catalog import SHOP_ITEM_CATALOG
from views.collection_view import (
    COLLECTION_STATUS_EQUIPPED,
    COLLECTION_STATUS_OWNED,
    COLLECTION_STATUS_UNOWNED,
    filter_collection_items_by_status,
)


def _catalog_items() -> list[dict]:
    return [
        item.model_dump(mode="json")
        for item in SHOP_ITEM_CATALOG
    ]


def _inventory(*item_keys: str) -> list[dict]:
    return [{"item_key": item_key} for item_key in item_keys]


def render_collection_test_page(shop_data, saved_room):
    from views.collection_view import render_shop_collection

    render_shop_collection(shop_data, saved_room)


class CollectionServiceTests(unittest.TestCase):
    def test_status_filter_keeps_catalog_order_and_ownership_meaning(self):
        items = [
            {"item_key": "owned"},
            {"item_key": "equipped"},
            {"item_key": "locked"},
        ]
        owned_keys = frozenset({"owned", "equipped"})
        equipped_keys = frozenset({"equipped"})

        self.assertEqual(
            [
                item["item_key"]
                for item in filter_collection_items_by_status(
                    items,
                    owned_keys=owned_keys,
                    equipped_keys=equipped_keys,
                    selected_status=COLLECTION_STATUS_OWNED,
                )
            ],
            ["owned", "equipped"],
        )
        self.assertEqual(
            [
                item["item_key"]
                for item in filter_collection_items_by_status(
                    items,
                    owned_keys=owned_keys,
                    equipped_keys=equipped_keys,
                    selected_status=COLLECTION_STATUS_EQUIPPED,
                )
            ],
            ["equipped"],
        )
        self.assertEqual(
            [
                item["item_key"]
                for item in filter_collection_items_by_status(
                    items,
                    owned_keys=owned_keys,
                    equipped_keys=equipped_keys,
                    selected_status=COLLECTION_STATUS_UNOWNED,
                )
            ],
            ["locked"],
        )
    def test_summary_counts_owned_and_equipped_items(self):
        summary = build_collection_summary(
            _catalog_items(),
            _inventory("desk_oak_basic", "decor_green_plant"),
            {
                "desk_item_key": "desk_oak_basic",
                "decor_left_item_key": "decor_green_plant",
            },
        )

        self.assertEqual(summary.total_count, 15)
        self.assertEqual(summary.owned_count, 2)
        self.assertEqual(summary.equipped_count, 2)
        self.assertEqual(summary.completion_percent, 13)
        self.assertEqual(
            summary.equipped_keys,
            frozenset({"desk_oak_basic", "decor_green_plant"}),
        )

        desk_progress = next(
            progress
            for progress in summary.category_progress
            if progress.category == "desk"
        )
        self.assertEqual(desk_progress.total_count, 3)
        self.assertEqual(desk_progress.owned_count, 1)
        self.assertEqual(desk_progress.completion_percent, 33)

    def test_summary_ignores_unknown_inventory_and_duplicate_equipment(self):
        summary = build_collection_summary(
            _catalog_items(),
            _inventory("desk_oak_basic", "retired_item"),
            {
                "desk_item_key": "desk_oak_basic",
                "chair_item_key": "desk_oak_basic",
            },
        )

        self.assertEqual(summary.owned_count, 1)
        self.assertEqual(summary.equipped_count, 1)

    def test_empty_catalog_has_zero_safe_progress(self):
        summary = build_collection_summary([], [], None)

        self.assertEqual(summary.total_count, 0)
        self.assertEqual(summary.owned_count, 0)
        self.assertEqual(summary.equipped_count, 0)
        self.assertEqual(summary.completion_percent, 0)
        self.assertTrue(
            all(
                progress.completion_percent == 0
                for progress in summary.category_progress
            )
        )


class CollectionViewTests(unittest.TestCase):
    def test_collection_renders_progress_and_is_read_only(self):
        shop_data = {
            "items": _catalog_items(),
            "inventory": _inventory(
                "desk_oak_basic",
                "decor_green_plant",
            ),
        }
        saved_room = {
            "desk_item_key": "desk_oak_basic",
        }

        app = AppTest.from_function(
            render_collection_test_page,
            args=(shop_data, saved_room),
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            [metric.label for metric in app.metric],
            ["수집한 아이템", "전체 수집률", "현재 장착"],
        )
        self.assertEqual(
            [metric.value for metric in app.metric],
            ["2/15개", "13%", "1개"],
        )
        self.assertIn(
            "컬렉션 카테고리",
            [selectbox.label for selectbox in app.selectbox],
        )
        self.assertIn(
            "보유 상태",
            [control.label for control in app.segmented_control],
        )
        self.assertEqual(list(app.button), [])
        self.assertTrue(
            any(
                message.value == "현재 학습방에 장착 중"
                for message in app.success
            )
        )
        self.assertTrue(
            any(
                message.value == "보유 중"
                for message in app.success
            )
        )


if __name__ == "__main__":
    unittest.main()
