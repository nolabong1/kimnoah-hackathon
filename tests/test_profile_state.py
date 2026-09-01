import unittest
from unittest.mock import patch

from views.profile_state import (
    PROFILE_LOADED_AT_KEY,
    PROFILE_SNAPSHOT_KEY,
    PROFILE_USER_ID_KEY,
    clear_profile_state,
    get_profile_snapshot,
    update_profile_snapshot,
)
from views.gamification_state import queue_gamification_notifications


USER_ID = "11111111-1111-4111-8111-111111111111"


def _profile() -> dict:
    return {
        "nickname": "학습자",
        "total_exp": 120,
        "level": 2,
        "current_streak": 3,
    }


class ProfileStateTests(unittest.TestCase):
    @patch("views.profile_state.get_profile", return_value=_profile())
    def test_reuses_current_user_snapshot_within_ttl(self, load_profile):
        state = {}

        first = get_profile_snapshot(object(), USER_ID, state, now=10.0)
        second = get_profile_snapshot(object(), USER_ID, state, now=20.0)

        self.assertEqual(first, second)
        load_profile.assert_called_once()

    @patch("views.profile_state.get_profile", return_value=_profile())
    def test_refreshes_expired_snapshot(self, load_profile):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: USER_ID,
            PROFILE_LOADED_AT_KEY: 10.0,
        }

        get_profile_snapshot(object(), USER_ID, state, now=40.0)

        load_profile.assert_called_once()

    @patch("views.profile_state.get_profile", return_value=_profile())
    def test_different_user_never_reuses_snapshot(self, load_profile):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: "22222222-2222-4222-8222-222222222222",
            PROFILE_LOADED_AT_KEY: 10.0,
        }

        get_profile_snapshot(object(), USER_ID, state, now=20.0)

        load_profile.assert_called_once()
        self.assertEqual(state[PROFILE_USER_ID_KEY], USER_ID)

    def test_server_result_updates_reward_values_immediately(self):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: USER_ID,
            PROFILE_LOADED_AT_KEY: 10.0,
        }

        updated = update_profile_snapshot(
            state,
            {
                "total_exp": 145,
                "level": 2,
                "current_streak": 4,
            },
            now=15.0,
        )

        self.assertTrue(updated)
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["nickname"], "학습자")
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["total_exp"], 145)
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["current_streak"], 4)
        self.assertEqual(state[PROFILE_LOADED_AT_KEY], 15.0)

    def test_partial_challenge_result_preserves_streak(self):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: USER_ID,
            PROFILE_LOADED_AT_KEY: 10.0,
        }

        updated = update_profile_snapshot(
            state,
            {"total_exp": 150, "level": 2},
            now=15.0,
        )

        self.assertTrue(updated)
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["total_exp"], 150)
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["current_streak"], 3)

    def test_gamification_result_refreshes_profile_snapshot(self):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: USER_ID,
            PROFILE_LOADED_AT_KEY: 10.0,
        }

        queue_gamification_notifications(
            state,
            {
                "total_exp": 160,
                "level": 2,
                "current_streak": 5,
                "newly_unlocked": [],
                "newly_completed_challenges": [],
            },
        )

        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["total_exp"], 160)
        self.assertEqual(state[PROFILE_SNAPSHOT_KEY]["current_streak"], 5)

    def test_logout_clear_preserves_unrelated_state(self):
        state = {
            PROFILE_SNAPSHOT_KEY: _profile(),
            PROFILE_USER_ID_KEY: USER_ID,
            PROFILE_LOADED_AT_KEY: 10.0,
            "tutor_active_session_id": "keep",
        }

        clear_profile_state(state)

        self.assertNotIn(PROFILE_SNAPSHOT_KEY, state)
        self.assertNotIn(PROFILE_USER_ID_KEY, state)
        self.assertNotIn(PROFILE_LOADED_AT_KEY, state)
        self.assertEqual(state["tutor_active_session_id"], "keep")


if __name__ == "__main__":
    unittest.main()
