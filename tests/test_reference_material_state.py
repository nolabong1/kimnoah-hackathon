import unittest
from unittest.mock import patch

from views.reference_material_state import (
    MATERIAL_LOADED_AT_KEY,
    MATERIAL_SNAPSHOTS_KEY,
    MATERIAL_USER_ID_KEY,
    SOURCE_BUNDLE_LOADED_AT_KEY,
    SOURCE_BUNDLE_SNAPSHOTS_KEY,
    clear_reference_material_state,
    get_reference_materials_snapshot,
    get_source_review_bundles_snapshot,
    invalidate_reference_material_snapshots,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _materials() -> tuple[list[dict], list[dict]]:
    return (
        [{"id": "source-1", "content_text": "원본 내용"}],
        [{"id": "review-1", "content_markdown": "# 복습자료"}],
    )


class ReferenceMaterialStateTests(unittest.TestCase):
    def test_reuses_plan_materials_within_ttl(self):
        calls = []

        def load_materials() -> tuple[list[dict], list[dict]]:
            calls.append(PLAN_ID)
            return _materials()

        state = {}
        first = get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=10.0, loader=load_materials
        )
        second = get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=20.0, loader=load_materials
        )

        self.assertEqual(first, second)
        self.assertEqual(calls, [PLAN_ID])

    @patch(
        "views.reference_material_state.get_learning_materials_by_plan",
        return_value=[],
    )
    @patch(
        "views.reference_material_state.get_review_materials_by_plan",
        return_value=[],
    )
    def test_empty_material_lists_are_cached(self, load_reviews, load_sources):
        state = {}

        get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=10.0
        )
        result = get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=20.0
        )

        self.assertEqual(result, ([], []))
        load_sources.assert_called_once()
        load_reviews.assert_called_once()

    def test_return_value_cannot_mutate_cached_materials(self):
        state = {}
        learning, _ = get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=10.0, loader=_materials
        )
        learning[0]["content_text"] = "변경"

        cached_learning, _ = get_reference_materials_snapshot(
            object(), USER_ID, PLAN_ID, state, now=20.0, loader=_materials
        )

        self.assertEqual(cached_learning[0]["content_text"], "원본 내용")

    def test_user_change_never_reuses_material_snapshot(self):
        state = {
            MATERIAL_SNAPSHOTS_KEY: {
                PLAN_ID: {"learning": _materials()[0], "review": _materials()[1]}
            },
            MATERIAL_LOADED_AT_KEY: {PLAN_ID: 10.0},
            MATERIAL_USER_ID_KEY: USER_ID,
        }
        calls = []

        get_reference_materials_snapshot(
            object(),
            "22222222-2222-4222-8222-222222222222",
            PLAN_ID,
            state,
            now=20.0,
            loader=lambda: (calls.append(PLAN_ID) or ([], [])),
        )

        self.assertEqual(calls, [PLAN_ID])
        self.assertEqual(
            state[MATERIAL_USER_ID_KEY],
            "22222222-2222-4222-8222-222222222222",
        )

    def test_reuses_source_review_bundles_within_ttl(self):
        calls = []
        bundles = [
            {
                "source_material": {"id": "source-1"},
                "review_material": {"id": "review-1"},
            }
        ]

        def load_bundles() -> list[dict]:
            calls.append(PLAN_ID)
            return bundles

        state = {}
        first = get_source_review_bundles_snapshot(
            object(), USER_ID, PLAN_ID, state, now=10.0, loader=load_bundles
        )
        first[0]["review_material"]["id"] = "changed"
        second = get_source_review_bundles_snapshot(
            object(), USER_ID, PLAN_ID, state, now=20.0, loader=load_bundles
        )

        self.assertEqual(second, bundles)
        self.assertEqual(calls, [PLAN_ID])

    def test_invalidation_and_logout_clear_preserve_unrelated_state(self):
        state = {
            MATERIAL_SNAPSHOTS_KEY: {
                PLAN_ID: {"learning": [], "review": []},
                "keep-plan": {"learning": [], "review": []},
            },
            MATERIAL_LOADED_AT_KEY: {PLAN_ID: 10.0, "keep-plan": 10.0},
            MATERIAL_USER_ID_KEY: USER_ID,
            SOURCE_BUNDLE_SNAPSHOTS_KEY: {
                PLAN_ID: [],
                "keep-plan": [],
            },
            SOURCE_BUNDLE_LOADED_AT_KEY: {
                PLAN_ID: 10.0,
                "keep-plan": 10.0,
            },
            "tutor_active_session_id": "keep",
        }

        invalidate_reference_material_snapshots(state, PLAN_ID)
        self.assertNotIn(PLAN_ID, state[MATERIAL_SNAPSHOTS_KEY])
        self.assertIn("keep-plan", state[MATERIAL_SNAPSHOTS_KEY])
        self.assertNotIn(PLAN_ID, state[SOURCE_BUNDLE_SNAPSHOTS_KEY])
        self.assertIn("keep-plan", state[SOURCE_BUNDLE_SNAPSHOTS_KEY])

        clear_reference_material_state(state)
        self.assertEqual(state, {"tutor_active_session_id": "keep"})


if __name__ == "__main__":
    unittest.main()
