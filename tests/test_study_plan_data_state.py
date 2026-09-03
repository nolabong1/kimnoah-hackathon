import unittest
from unittest.mock import patch

from models.learning_objective import StoredLearningObjective
from views.study_plan_data_state import (
    OBJECTIVE_LOADED_AT_KEY,
    OBJECTIVE_SNAPSHOTS_KEY,
    OBJECTIVE_USER_ID_KEY,
    PLAN_LIST_LOADED_AT_KEY,
    PLAN_LIST_SNAPSHOT_KEY,
    PLAN_LIST_USER_ID_KEY,
    TASK_LOADED_AT_KEY,
    TASK_SNAPSHOTS_KEY,
    TASK_USER_ID_KEY,
    clear_study_plan_data_state,
    get_learning_objectives_by_plan_ids_snapshot,
    get_study_plan_list_snapshot,
    get_study_plan_tasks_snapshot,
    get_study_tasks_by_plan_ids_snapshot,
    invalidate_learning_objective_snapshots,
    invalidate_study_plan_list_snapshot,
    invalidate_study_task_snapshots,
)


USER_ID = "11111111-1111-4111-8111-111111111111"


def _plans() -> list[dict]:
    return [
        {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "title": "파이썬 7일 계획",
            "available_schedule": {"monday": 60},
        }
    ]


def _tasks(plan_id: str) -> list[dict]:
    return [{"id": f"task-for-{plan_id}", "status": "pending"}]


def _objectives(plan_id: str) -> list[StoredLearningObjective]:
    objective_id = (
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        if plan_id.startswith("a")
        else "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    )
    return [
        StoredLearningObjective.model_validate(
            {
                "id": objective_id,
                "user_id": USER_ID,
                "plan_id": plan_id,
                "objective_key": "python_conditionals",
                "title": "조건문의 실행 흐름",
                "description": "조건식에 따른 분기 흐름을 설명하고 적용한다.",
                "target_depth": "developing",
                "evidence_requirements": [
                    {"key": "explain", "description": "흐름을 설명한다."},
                    {"key": "apply", "description": "코드를 작성한다."},
                    {
                        "key": "differentiate",
                        "description": "분기 차이를 구분한다.",
                    },
                ],
                "contract_hash": "0" * 64,
                "sort_order": 1,
                "origin": "generated",
            }
        )
    ]


class StudyPlanDataStateTests(unittest.TestCase):
    @patch(
        "views.study_plan_data_state.get_user_study_plans",
        return_value=_plans(),
    )
    def test_reuses_current_user_plan_list_within_ttl(self, load_plans):
        state = {}

        first = get_study_plan_list_snapshot(
            object(), USER_ID, state, now=10.0
        )
        second = get_study_plan_list_snapshot(
            object(), USER_ID, state, now=20.0
        )

        self.assertEqual(first, second)
        load_plans.assert_called_once()

    @patch(
        "views.study_plan_data_state.get_user_study_plans",
        return_value=_plans(),
    )
    def test_refreshes_expired_plan_list(self, load_plans):
        state = {
            PLAN_LIST_SNAPSHOT_KEY: _plans(),
            PLAN_LIST_USER_ID_KEY: USER_ID,
            PLAN_LIST_LOADED_AT_KEY: 10.0,
        }

        get_study_plan_list_snapshot(object(), USER_ID, state, now=40.0)

        load_plans.assert_called_once()

    @patch(
        "views.study_plan_data_state.get_user_study_plans",
        return_value=[],
    )
    def test_empty_plan_list_is_cached(self, load_plans):
        state = {}

        get_study_plan_list_snapshot(object(), USER_ID, state, now=10.0)
        result = get_study_plan_list_snapshot(
            object(), USER_ID, state, now=20.0
        )

        self.assertEqual(result, [])
        load_plans.assert_called_once()

    @patch(
        "views.study_plan_data_state.get_user_study_plans",
        return_value=_plans(),
    )
    def test_different_user_never_reuses_plan_list(self, load_plans):
        state = {
            PLAN_LIST_SNAPSHOT_KEY: _plans(),
            PLAN_LIST_USER_ID_KEY: "22222222-2222-4222-8222-222222222222",
            PLAN_LIST_LOADED_AT_KEY: 10.0,
        }

        get_study_plan_list_snapshot(object(), USER_ID, state, now=20.0)

        load_plans.assert_called_once()
        self.assertEqual(state[PLAN_LIST_USER_ID_KEY], USER_ID)

    @patch(
        "views.study_plan_data_state.get_user_study_plans",
        return_value=_plans(),
    )
    def test_return_value_cannot_mutate_cached_nested_data(self, load_plans):
        state = {}

        first = get_study_plan_list_snapshot(
            object(), USER_ID, state, now=10.0
        )
        first[0]["available_schedule"]["monday"] = 0
        second = get_study_plan_list_snapshot(
            object(), USER_ID, state, now=20.0
        )

        self.assertEqual(second[0]["available_schedule"]["monday"], 60)
        load_plans.assert_called_once()

    def test_invalidation_and_logout_clear_preserve_unrelated_state(self):
        state = {
            PLAN_LIST_SNAPSHOT_KEY: _plans(),
            PLAN_LIST_USER_ID_KEY: USER_ID,
            PLAN_LIST_LOADED_AT_KEY: 10.0,
            "tutor_active_session_id": "keep",
        }

        invalidate_study_plan_list_snapshot(state)
        self.assertEqual(state, {"tutor_active_session_id": "keep"})

        state[PLAN_LIST_SNAPSHOT_KEY] = _plans()
        clear_study_plan_data_state(state)
        self.assertEqual(state, {"tutor_active_session_id": "keep"})

    def test_batch_task_cache_loads_only_missing_or_expired_plans(self):
        first_plan_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second_plan_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        calls = []

        def load_tasks(plan_ids: list[str]) -> dict[str, list[dict]]:
            calls.append(plan_ids)
            return {plan_id: _tasks(plan_id) for plan_id in plan_ids}

        state = {}
        get_study_tasks_by_plan_ids_snapshot(
            object(),
            USER_ID,
            [first_plan_id],
            state,
            now=10.0,
            loader=load_tasks,
        )
        result = get_study_tasks_by_plan_ids_snapshot(
            object(),
            USER_ID,
            [first_plan_id, second_plan_id],
            state,
            now=20.0,
            loader=load_tasks,
        )

        self.assertEqual(calls, [[first_plan_id], [second_plan_id]])
        self.assertEqual(result[first_plan_id], _tasks(first_plan_id))
        self.assertEqual(result[second_plan_id], _tasks(second_plan_id))

    def test_single_plan_task_cache_returns_defensive_copy(self):
        plan_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        calls = []

        def load_tasks() -> list[dict]:
            calls.append(plan_id)
            return _tasks(plan_id)

        state = {}
        first = get_study_plan_tasks_snapshot(
            object(),
            USER_ID,
            plan_id,
            state,
            now=10.0,
            loader=load_tasks,
        )
        first[0]["status"] = "completed"
        second = get_study_plan_tasks_snapshot(
            object(),
            USER_ID,
            plan_id,
            state,
            now=20.0,
            loader=load_tasks,
        )

        self.assertEqual(second[0]["status"], "pending")
        self.assertEqual(calls, [plan_id])

    def test_task_cache_is_user_scoped_and_supports_exact_invalidation(self):
        first_plan_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second_plan_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        state = {
            TASK_SNAPSHOTS_KEY: {
                first_plan_id: _tasks(first_plan_id),
                second_plan_id: _tasks(second_plan_id),
            },
            TASK_LOADED_AT_KEY: {
                first_plan_id: 10.0,
                second_plan_id: 10.0,
            },
            TASK_USER_ID_KEY: USER_ID,
            "tutor_active_session_id": "keep",
        }

        invalidate_study_task_snapshots(state, first_plan_id)

        self.assertNotIn(first_plan_id, state[TASK_SNAPSHOTS_KEY])
        self.assertIn(second_plan_id, state[TASK_SNAPSHOTS_KEY])
        self.assertEqual(state["tutor_active_session_id"], "keep")

        get_study_plan_tasks_snapshot(
            object(),
            "22222222-2222-4222-8222-222222222222",
            second_plan_id,
            state,
            now=20.0,
            loader=lambda: [],
        )
        self.assertEqual(
            state[TASK_USER_ID_KEY],
            "22222222-2222-4222-8222-222222222222",
        )

    def test_objective_cache_loads_only_missing_plans_and_returns_copy(self):
        first_plan_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second_plan_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        calls = []

        def load_objectives(plan_ids):
            calls.append(plan_ids)
            return {
                plan_id: _objectives(plan_id)
                for plan_id in plan_ids
            }

        state = {}
        first = get_learning_objectives_by_plan_ids_snapshot(
            object(),
            USER_ID,
            [first_plan_id],
            state,
            now=10.0,
            loader=load_objectives,
        )
        first[first_plan_id][0].title = "변경된 제목"
        result = get_learning_objectives_by_plan_ids_snapshot(
            object(),
            USER_ID,
            [first_plan_id, second_plan_id],
            state,
            now=20.0,
            loader=load_objectives,
        )

        self.assertEqual(calls, [[first_plan_id], [second_plan_id]])
        self.assertEqual(result[first_plan_id][0].title, "조건문의 실행 흐름")
        self.assertEqual(
            str(result[second_plan_id][0].plan_id),
            second_plan_id,
        )

    def test_objective_cache_is_user_scoped_and_exactly_invalidated(self):
        first_plan_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        second_plan_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        state = {
            OBJECTIVE_SNAPSHOTS_KEY: {
                first_plan_id: _objectives(first_plan_id),
                second_plan_id: _objectives(second_plan_id),
            },
            OBJECTIVE_LOADED_AT_KEY: {
                first_plan_id: 10.0,
                second_plan_id: 10.0,
            },
            OBJECTIVE_USER_ID_KEY: USER_ID,
            "tutor_active_session_id": "keep",
        }

        invalidate_learning_objective_snapshots(state, first_plan_id)

        self.assertNotIn(first_plan_id, state[OBJECTIVE_SNAPSHOTS_KEY])
        self.assertIn(second_plan_id, state[OBJECTIVE_SNAPSHOTS_KEY])
        self.assertEqual(state["tutor_active_session_id"], "keep")

        other_user_id = "22222222-2222-4222-8222-222222222222"
        get_learning_objectives_by_plan_ids_snapshot(
            object(),
            other_user_id,
            [second_plan_id],
            state,
            now=20.0,
            loader=lambda plan_ids: {plan_ids[0]: []},
        )
        self.assertEqual(state[OBJECTIVE_USER_ID_KEY], other_user_id)


if __name__ == "__main__":
    unittest.main()
