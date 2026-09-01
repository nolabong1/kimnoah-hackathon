import unittest
from unittest.mock import patch

from views.gamification_view import execute_challenge_reward_claim
from views.interaction_state import INTERACTION_QUEUE_KEY


class ChallengeRewardInteractionTests(unittest.TestCase):
    def test_claim_calls_rpc_once_and_queues_new_reward(self):
        supabase = object()
        state = {}
        result = {
            "challenge_id": "challenge-1",
            "status": "claimed",
            "reward_exp": 15,
            "total_exp": 215,
            "level": 3,
            "already_claimed": False,
        }

        with patch(
            "views.gamification_view.claim_challenge_reward",
            return_value=result,
        ) as claim:
            returned = execute_challenge_reward_claim(
                supabase,
                "challenge-1",
                state,
            )

        claim.assert_called_once_with(supabase, "challenge-1")
        self.assertEqual(returned, result)
        self.assertEqual(
            state[INTERACTION_QUEUE_KEY][0]["kind"],
            "challenge_reward_claimed",
        )

    def test_duplicate_claim_does_not_queue_reward_feedback(self):
        state = {}

        with patch(
            "views.gamification_view.claim_challenge_reward",
            return_value={
                "challenge_id": "challenge-1",
                "status": "claimed",
                "reward_exp": 0,
                "total_exp": 215,
                "level": 3,
                "already_claimed": True,
            },
        ):
            execute_challenge_reward_claim(
                object(),
                "challenge-1",
                state,
            )

        self.assertNotIn(INTERACTION_QUEUE_KEY, state)


if __name__ == "__main__":
    unittest.main()
