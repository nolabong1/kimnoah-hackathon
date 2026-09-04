from pathlib import Path
import re
import unittest

from services.reward_policy import (
    DAILY_COMPLETION_BONUS_EXP,
    EXP_PER_LEVEL,
    TASK_COMPLETION_EXP,
    calculate_level,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RewardPolicyTests(unittest.TestCase):
    def test_level_boundaries_match_the_current_policy(self) -> None:
        self.assertEqual(calculate_level(0), 1)
        self.assertEqual(calculate_level(EXP_PER_LEVEL - 1), 1)
        self.assertEqual(calculate_level(EXP_PER_LEVEL), 2)

    def test_invalid_total_exp_is_rejected(self) -> None:
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_level(value)  # type: ignore[arg-type]

    def test_python_policy_matches_task_completion_rpc(self) -> None:
        migration = (
            PROJECT_ROOT / "supabase_task_completion.sql"
        ).read_text(encoding="utf-8")

        task_pattern = re.compile(
            r"'task_completion'\s*,\s*"
            r"'task:'\s*\|\|\s*v_task\.id::text\s*,\s*"
            rf"{TASK_COMPLETION_EXP}\s*\)",
            re.MULTILINE,
        )
        daily_pattern = re.compile(
            r"'daily_completion'\s*,\s*"
            r"'daily:'\s*\|\|\s*v_today::text\s*,\s*"
            rf"{DAILY_COMPLETION_BONUS_EXP}\s*\)",
            re.MULTILINE,
        )
        level_formula = (
            f"level = (v_new_total_exp / {EXP_PER_LEVEL}) + 1"
        )

        self.assertRegex(migration, task_pattern)
        self.assertRegex(migration, daily_pattern)
        self.assertIn(level_formula, migration)


if __name__ == "__main__":
    unittest.main()
