import unittest
from unittest.mock import Mock

from views.shop_state import (
    ROOM_DATA_LOADED_AT_KEY,
    ROOM_DATA_SNAPSHOT_KEY,
    ROOM_DATA_USER_ID_KEY,
    SHOP_DATA_LOADED_AT_KEY,
    SHOP_DATA_SNAPSHOT_KEY,
    SHOP_DATA_USER_ID_KEY,
    get_room_data_snapshot,
    get_shop_data_snapshot,
    invalidate_shop_data_snapshot,
    invalidate_shop_snapshots,
    update_room_data_snapshot,
)


USER_ID = "11111111-1111-4111-8111-111111111111"


class ShopDataStateTests(unittest.TestCase):
    def test_shop_data_is_reused_within_ttl(self):
        state = {}
        loader = Mock(
            return_value={"wallet": {}, "items": [], "inventory": []}
        )

        first = get_shop_data_snapshot(state, USER_ID, loader, now=10.0)
        second = get_shop_data_snapshot(state, USER_ID, loader, now=20.0)

        self.assertEqual(first, second)
        loader.assert_called_once()

    def test_shop_data_refreshes_after_ttl(self):
        state = {
            SHOP_DATA_SNAPSHOT_KEY: {
                "wallet": {},
                "items": [],
                "inventory": [],
            },
            SHOP_DATA_USER_ID_KEY: USER_ID,
            SHOP_DATA_LOADED_AT_KEY: 10.0,
        }
        loader = Mock(
            return_value={"wallet": {}, "items": [], "inventory": []}
        )

        get_shop_data_snapshot(state, USER_ID, loader, now=40.0)

        loader.assert_called_once()

    def test_empty_room_result_is_cached(self):
        state = {}
        loader = Mock(return_value=None)

        first = get_room_data_snapshot(state, USER_ID, loader, now=10.0)
        second = get_room_data_snapshot(state, USER_ID, loader, now=20.0)

        self.assertIsNone(first)
        self.assertIsNone(second)
        loader.assert_called_once()

    def test_saved_room_updates_current_user_snapshot(self):
        state = {
            ROOM_DATA_SNAPSHOT_KEY: None,
            ROOM_DATA_USER_ID_KEY: USER_ID,
            ROOM_DATA_LOADED_AT_KEY: 10.0,
        }
        room = {"user_id": USER_ID, "updated_at": "saved"}

        updated = update_room_data_snapshot(state, room, now=15.0)

        self.assertTrue(updated)
        self.assertEqual(state[ROOM_DATA_SNAPSHOT_KEY], room)
        self.assertEqual(state[ROOM_DATA_LOADED_AT_KEY], 15.0)

    def test_purchase_invalidation_preserves_room_snapshot(self):
        state = {
            SHOP_DATA_SNAPSHOT_KEY: {"wallet": {}},
            SHOP_DATA_USER_ID_KEY: USER_ID,
            SHOP_DATA_LOADED_AT_KEY: 10.0,
            ROOM_DATA_SNAPSHOT_KEY: {"user_id": USER_ID},
            ROOM_DATA_USER_ID_KEY: USER_ID,
            ROOM_DATA_LOADED_AT_KEY: 10.0,
        }

        invalidate_shop_data_snapshot(state)

        self.assertNotIn(SHOP_DATA_SNAPSHOT_KEY, state)
        self.assertIn(ROOM_DATA_SNAPSHOT_KEY, state)

    def test_test_tool_invalidation_clears_both_snapshots(self):
        state = {
            SHOP_DATA_SNAPSHOT_KEY: {"wallet": {}},
            SHOP_DATA_USER_ID_KEY: USER_ID,
            SHOP_DATA_LOADED_AT_KEY: 10.0,
            ROOM_DATA_SNAPSHOT_KEY: {"user_id": USER_ID},
            ROOM_DATA_USER_ID_KEY: USER_ID,
            ROOM_DATA_LOADED_AT_KEY: 10.0,
            "profile_snapshot_data": {"nickname": "keep"},
        }

        invalidate_shop_snapshots(state)

        self.assertNotIn(SHOP_DATA_SNAPSHOT_KEY, state)
        self.assertNotIn(ROOM_DATA_SNAPSHOT_KEY, state)
        self.assertIn("profile_snapshot_data", state)


if __name__ == "__main__":
    unittest.main()
