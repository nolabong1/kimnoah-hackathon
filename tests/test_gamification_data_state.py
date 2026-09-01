import unittest
from unittest.mock import Mock

from views.gamification_state import (
    DATA_LOADED_AT_KEY,
    DATA_SNAPSHOT_KEY,
    DATA_USER_ID_KEY,
    get_gamification_data_snapshot,
    invalidate_gamification_data_snapshot,
    queue_gamification_notifications,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
SNAPSHOT = {
    "achievements": [{"achievement_key": "first_task"}],
    "challenges": [{"id": "challenge-1"}],
    "showcase": [{"slot": 1}],
}


class GamificationDataStateTests(unittest.TestCase):
    def test_snapshot_is_reused_within_ttl(self):
        state = {}
        loader = Mock(return_value=SNAPSHOT)

        first = get_gamification_data_snapshot(
            state,
            USER_ID,
            loader,
            now=10.0,
        )
        second = get_gamification_data_snapshot(
            state,
            USER_ID,
            loader,
            now=20.0,
        )

        self.assertEqual(first, second)
        loader.assert_called_once()

    def test_snapshot_refreshes_after_ttl(self):
        state = {
            DATA_SNAPSHOT_KEY: SNAPSHOT,
            DATA_USER_ID_KEY: USER_ID,
            DATA_LOADED_AT_KEY: 10.0,
        }
        loader = Mock(return_value=SNAPSHOT)

        get_gamification_data_snapshot(
            state,
            USER_ID,
            loader,
            now=40.0,
        )

        loader.assert_called_once()

    def test_snapshot_is_scoped_to_user(self):
        state = {
            DATA_SNAPSHOT_KEY: SNAPSHOT,
            DATA_USER_ID_KEY: USER_ID,
            DATA_LOADED_AT_KEY: 10.0,
        }
        loader = Mock(return_value=SNAPSHOT)

        get_gamification_data_snapshot(
            state,
            "22222222-2222-4222-8222-222222222222",
            loader,
            now=20.0,
        )

        loader.assert_called_once()

    def test_returned_rows_do_not_mutate_cached_rows(self):
        state = {}
        loader = Mock(return_value=SNAPSHOT)

        first = get_gamification_data_snapshot(
            state,
            USER_ID,
            loader,
            now=10.0,
        )
        first["achievements"][0]["achievement_key"] = "changed"
        second = get_gamification_data_snapshot(
            state,
            USER_ID,
            loader,
            now=20.0,
        )

        self.assertEqual(
            second["achievements"][0]["achievement_key"],
            "first_task",
        )

    def test_explicit_invalidation_preserves_other_feature_state(self):
        state = {
            DATA_SNAPSHOT_KEY: SNAPSHOT,
            DATA_USER_ID_KEY: USER_ID,
            DATA_LOADED_AT_KEY: 10.0,
            "shop_data_snapshot": {"wallet": {}},
        }

        invalidate_gamification_data_snapshot(state)

        self.assertNotIn(DATA_SNAPSHOT_KEY, state)
        self.assertIn("shop_data_snapshot", state)

    def test_valid_sync_result_invalidates_cached_progress(self):
        state = {
            DATA_SNAPSHOT_KEY: SNAPSHOT,
            DATA_USER_ID_KEY: USER_ID,
            DATA_LOADED_AT_KEY: 10.0,
        }

        queue_gamification_notifications(
            state,
            {
                "newly_unlocked": [],
                "newly_completed_challenges": [],
            },
        )

        self.assertNotIn(DATA_SNAPSHOT_KEY, state)


if __name__ == "__main__":
    unittest.main()
