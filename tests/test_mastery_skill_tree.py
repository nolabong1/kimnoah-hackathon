import unittest

from views.mastery_skill_tree_component import (
    MAX_SKILL_TREE_NODES,
    build_mastery_skill_tree_nodes,
)


def _mastery(
    concept_id: str,
    name: str,
    score: int,
    *,
    is_weak: bool,
    consecutive_incorrect_count: int = 0,
) -> dict:
    return {
        "concept_id": concept_id,
        "concept_name": name,
        "mastery_score": score,
        "correct_count": 2,
        "incorrect_count": 1,
        "consecutive_incorrect_count": consecutive_incorrect_count,
        "last_answer_correct": score >= 60,
        "last_assessed_at": "2026-08-31T01:30:00+00:00",
        "is_weak": is_weak,
    }


class MasterySkillTreeTests(unittest.TestCase):
    def test_weak_low_score_concepts_are_first_and_only_first_is_recommended(self):
        nodes = build_mastery_skill_tree_nodes(
            [
                _mastery("stable", "함수", 80, is_weak=False),
                _mastery("weak-high", "조건문", 45, is_weak=True),
                _mastery("weak-low", "반복문", 25, is_weak=True),
            ]
        )

        self.assertEqual(
            [node["id"] for node in nodes],
            ["weak-low", "weak-high", "stable"],
        )
        self.assertEqual(
            [node["recommended"] for node in nodes],
            [True, False, False],
        )
        self.assertEqual(nodes[0]["status_label"], "복습 필요")
        self.assertEqual(nodes[-1]["status_label"], "기준 이상")

    def test_tree_is_limited_without_mutating_input(self):
        masteries = [
            _mastery(str(index), f"개념 {index}", index, is_weak=True)
            for index in range(MAX_SKILL_TREE_NODES + 3)
        ]

        nodes = build_mastery_skill_tree_nodes(masteries)

        self.assertEqual(len(nodes), MAX_SKILL_TREE_NODES)
        self.assertNotIn("rank", masteries[0])

    def test_duplicate_concept_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "중복된 개념"):
            build_mastery_skill_tree_nodes(
                [
                    _mastery("same", "반복문", 30, is_weak=True),
                    _mastery("same", "조건문", 40, is_weak=True),
                ]
            )

    def test_invalid_score_is_rejected(self):
        invalid = _mastery("concept", "반복문", 30, is_weak=True)
        invalid["mastery_score"] = 101

        with self.assertRaisesRegex(ValueError, "숙련도 점수"):
            build_mastery_skill_tree_nodes([invalid])

    def test_timestamp_is_shown_in_seoul_time(self):
        node = build_mastery_skill_tree_nodes(
            [_mastery("concept", "반복문", 30, is_weak=True)]
        )[0]

        self.assertEqual(node["last_assessed_at"], "2026-08-31 10:30")


if __name__ == "__main__":
    unittest.main()
