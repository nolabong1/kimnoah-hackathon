import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from models.gamification import (
    AchievementDefinition,
    AchievementTier,
    ChallengeEligibilityContext,
    ChallengePeriodType,
    ChallengeStatus,
    CompletedPlanFact,
    CompletedTaskFact,
    QuizSubmissionFact,
)
from services.gamification_catalog import (
    ACHIEVEMENT_CATALOG,
    CHALLENGE_TEMPLATE_CATALOG,
)
from services.gamification_service import (
    GamificationValidationError,
    calculate_achievement_metrics,
    calculate_period_metrics,
    clamp_progress,
    evaluate_achievement_progress,
    evaluate_challenge_progress,
    get_period_window,
    mask_achievement_definition,
    select_challenge_templates,
)
from services.gamification_repository import (
    claim_challenge_reward,
    equip_badge,
    get_badge_showcase,
    get_user_achievements,
    get_user_challenges,
    remove_badge,
    sync_gamification_state,
)
from services.study_plan_repository import complete_study_task
from models.gamification import GamificationMetric
from views.gamification_state import (
    NOTIFICATION_QUEUE_KEY,
    clear_gamification_state,
    pop_gamification_notifications,
    queue_gamification_notifications,
)


UTC = timezone.utc
USER_ID = "00000000-0000-0000-0000-000000000001"
TASK_ID = "00000000-0000-0000-0000-000000000002"
ACHIEVEMENT_ID = "00000000-0000-0000-0000-000000000003"
CHALLENGE_ID = "00000000-0000-0000-0000-000000000004"


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRequest:
    def __init__(self, data):
        self.data = data
        self.selected = None
        self.filters = {}
        self.orders = []

    def select(self, fields):
        self.selected = fields
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def order(self, field, desc=False):
        self.orders.append((field, desc))
        return self

    def execute(self):
        return FakeResponse(self.data)


class FakeSupabase:
    def __init__(self, *, rpc_results=None, table_results=None):
        self.rpc_results = rpc_results or {}
        self.table_results = table_results or {}
        self.rpc_calls = []
        self.table_requests = {}

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        result = self.rpc_results[function_name]
        if isinstance(result, Exception):
            raise result
        if isinstance(result, list):
            result = result.pop(0)
        return FakeRequest(result)

    def table(self, table_name):
        request = FakeRequest(self.table_results.get(table_name, []))
        self.table_requests[table_name] = request
        return request


def gamification_sync_result(**overrides) -> dict:
    result = {
        "total_exp": 100,
        "level": 2,
        "current_streak": 1,
        "achievement_exp_awarded": 0,
        "newly_unlocked": [],
        "newly_completed_challenges": [],
    }
    result.update(overrides)
    return result


def task_fact(
    task_id: str,
    *,
    task_type: str = "learn",
    completed_at: datetime | None = None,
) -> CompletedTaskFact:
    return CompletedTaskFact(
        task_id=task_id,
        task_type=task_type,
        completed_at=completed_at
        or datetime(2026, 8, 16, 1, 0, tzinfo=UTC),
    )


def quiz_fact(
    attempt_id: str,
    quiz_id: str,
    *,
    is_perfect: bool = False,
    submitted_at: datetime | None = None,
) -> QuizSubmissionFact:
    return QuizSubmissionFact(
        attempt_id=attempt_id,
        quiz_id=quiz_id,
        is_perfect=is_perfect,
        submitted_at=submitted_at
        or datetime(2026, 8, 16, 2, 0, tzinfo=UTC),
    )


def plan_fact(
    plan_id: str,
    task_types: frozenset[str],
    *,
    completed_at: datetime | None = None,
) -> CompletedPlanFact:
    return CompletedPlanFact(
        plan_id=plan_id,
        completed_task_types=task_types,
        completed_at=completed_at
        or datetime(2026, 8, 16, 3, 0, tzinfo=UTC),
    )


class AchievementCatalogTests(unittest.TestCase):
    def test_catalog_keys_badges_and_sort_positions_are_unique(self):
        achievement_keys = [item.key for item in ACHIEVEMENT_CATALOG]
        badge_keys = [item.badge.key for item in ACHIEVEMENT_CATALOG]
        sort_positions = [item.sort_order for item in ACHIEVEMENT_CATALOG]

        self.assertEqual(len(achievement_keys), len(set(achievement_keys)))
        self.assertEqual(len(badge_keys), len(set(badge_keys)))
        self.assertEqual(len(sort_positions), len(set(sort_positions)))
        self.assertEqual(len(ACHIEVEMENT_CATALOG), 13)

    def test_catalog_fields_and_rewards_are_valid(self):
        for definition in ACHIEVEMENT_CATALOG:
            self.assertTrue(definition.name_ko.strip())
            self.assertTrue(definition.description_ko.strip())
            self.assertGreater(definition.target_value, 0)
            self.assertGreater(definition.reward_exp, 0)
            self.assertTrue(definition.badge.name_ko.strip())
            self.assertTrue(definition.badge.icon.strip())

    def test_tiered_series_thresholds_increase(self):
        tier_order = {
            AchievementTier.BRONZE: 0,
            AchievementTier.SILVER: 1,
            AchievementTier.GOLD: 2,
            AchievementTier.PLATINUM: 3,
        }
        series: dict[str, list[AchievementDefinition]] = {}
        for definition in ACHIEVEMENT_CATALOG:
            series.setdefault(definition.series_key, []).append(definition)

        for definitions in series.values():
            ordered = sorted(definitions, key=lambda item: tier_order[item.tier])
            thresholds = [item.target_value for item in ordered]
            self.assertEqual(thresholds, sorted(set(thresholds)))

    def test_hidden_achievement_is_masked_until_unlocked(self):
        hidden = ACHIEVEMENT_CATALOG[0].model_copy(update={"hidden": True})

        locked_view = mask_achievement_definition(hidden, is_unlocked=False)
        unlocked_view = mask_achievement_definition(hidden, is_unlocked=True)

        self.assertEqual(locked_view["name_ko"], "비밀 업적")
        self.assertIsNone(locked_view["target_value"])
        self.assertIsNone(locked_view["badge"]["key"])
        self.assertEqual(unlocked_view["name_ko"], hidden.name_ko)
        self.assertEqual(unlocked_view["target_value"], hidden.target_value)

    def test_challenge_catalog_keys_and_sort_positions_are_unique(self):
        template_keys = [item.key for item in CHALLENGE_TEMPLATE_CATALOG]
        sort_positions = [item.sort_order for item in CHALLENGE_TEMPLATE_CATALOG]

        self.assertEqual(len(template_keys), len(set(template_keys)))
        self.assertEqual(len(sort_positions), len(set(sort_positions)))
        for template in CHALLENGE_TEMPLATE_CATALOG:
            self.assertTrue(template.name_ko.strip())
            self.assertTrue(template.description_ko.strip())
            self.assertGreater(template.target_value, 0)
            self.assertGreater(template.reward_exp, 0)


class ProgressCalculationTests(unittest.TestCase):
    def test_zero_and_one_completed_task(self):
        empty_metrics = calculate_achievement_metrics(
            [], [], [], longest_streak=0
        )
        one_task_metrics = calculate_achievement_metrics(
            [task_fact("task-1")], [], [], longest_streak=0
        )

        self.assertEqual(empty_metrics[GamificationMetric.COMPLETED_TASKS], 0)
        self.assertEqual(one_task_metrics[GamificationMetric.COMPLETED_TASKS], 1)

    def test_repeated_task_completion_does_not_farm_progress(self):
        completion = task_fact("task-1", task_type="review")
        metrics = calculate_achievement_metrics(
            [completion, completion], [], [], longest_streak=0
        )

        self.assertEqual(metrics[GamificationMetric.COMPLETED_TASKS], 1)
        self.assertEqual(
            metrics[GamificationMetric.COMPLETED_REVIEW_TASKS],
            1,
        )

    def test_conflicting_duplicate_task_is_rejected(self):
        with self.assertRaises(GamificationValidationError):
            calculate_achievement_metrics(
                [
                    task_fact("task-1", task_type="learn"),
                    task_fact("task-1", task_type="review"),
                ],
                [],
                [],
                longest_streak=0,
            )

    def test_zero_task_plan_cannot_be_constructed(self):
        with self.assertRaises(ValidationError):
            plan_fact("empty-plan", frozenset())

    def test_plan_quiz_review_and_streak_metrics(self):
        metrics = calculate_achievement_metrics(
            [task_fact("review-1", task_type="review")],
            [
                quiz_fact("attempt-1", "quiz-1", is_perfect=True),
                quiz_fact("attempt-2", "quiz-1", is_perfect=False),
            ],
            [
                plan_fact("plan-1", frozenset({"learn"})),
                plan_fact(
                    "plan-2",
                    frozenset({"learn", "review", "quiz"}),
                ),
            ],
            longest_streak=7,
        )

        self.assertEqual(metrics[GamificationMetric.COMPLETED_PLANS], 2)
        self.assertEqual(metrics[GamificationMetric.QUIZ_SUBMISSIONS], 2)
        self.assertEqual(metrics[GamificationMetric.PERFECT_QUIZZES], 1)
        self.assertEqual(
            metrics[GamificationMetric.BALANCED_COMPLETED_PLANS],
            1,
        )
        self.assertEqual(metrics[GamificationMetric.LONGEST_STREAK], 7)

    def test_progress_clamping_and_permanent_unlock(self):
        definition = ACHIEVEMENT_CATALOG[1]
        self.assertEqual(clamp_progress(-5, 10), 0)
        self.assertEqual(clamp_progress(30, 10), 10)

        progress = evaluate_achievement_progress(
            definition,
            {definition.metric: 0},
            previously_unlocked=True,
        )
        self.assertTrue(progress.is_unlocked)
        self.assertFalse(progress.newly_unlocked)

    def test_multiple_qualifying_achievements_are_independent(self):
        metrics = {GamificationMetric.COMPLETED_TASKS: 60}
        task_definitions = [
            definition
            for definition in ACHIEVEMENT_CATALOG
            if definition.metric == GamificationMetric.COMPLETED_TASKS
        ]
        results = [
            evaluate_achievement_progress(definition, metrics)
            for definition in task_definitions
        ]

        self.assertEqual(sum(result.newly_unlocked for result in results), 3)


class PeriodTests(unittest.TestCase):
    def test_daily_boundary_uses_seoul_midnight(self):
        before_midnight = get_period_window(
            ChallengePeriodType.DAILY,
            datetime(2026, 8, 16, 14, 59, tzinfo=UTC),
        )
        after_midnight = get_period_window(
            ChallengePeriodType.DAILY,
            datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(
            before_midnight.start_at,
            datetime(2026, 8, 15, 15, 0, tzinfo=UTC),
        )
        self.assertEqual(
            after_midnight.start_at,
            datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

    def test_weekly_boundary_is_monday_in_seoul(self):
        sunday = get_period_window(
            ChallengePeriodType.WEEKLY,
            datetime(2026, 8, 16, 14, 59, tzinfo=UTC),
        )
        monday = get_period_window(
            ChallengePeriodType.WEEKLY,
            datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(
            sunday.start_at,
            datetime(2026, 8, 9, 15, 0, tzinfo=UTC),
        )
        self.assertEqual(
            monday.start_at,
            datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

    def test_naive_current_time_is_rejected(self):
        with self.assertRaises(GamificationValidationError):
            get_period_window(
                ChallengePeriodType.DAILY,
                datetime(2026, 8, 16, 12, 0),
            )


class ChallengeLogicTests(unittest.TestCase):
    def test_daily_and_weekly_counts_respect_limits(self):
        context = ChallengeEligibilityContext(
            available_task_count=20,
            available_review_task_count=3,
            available_quiz_count=3,
            available_study_day_count=7,
            completable_plan_count=2,
        )
        now = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)

        daily = select_challenge_templates(
            user_id="user-1",
            window=get_period_window(ChallengePeriodType.DAILY, now),
            templates=CHALLENGE_TEMPLATE_CATALOG,
            context=context,
        )
        weekly = select_challenge_templates(
            user_id="user-1",
            window=get_period_window(ChallengePeriodType.WEEKLY, now),
            templates=CHALLENGE_TEMPLATE_CATALOG,
            context=context,
        )

        self.assertLessEqual(len(daily), 3)
        self.assertLessEqual(len(weekly), 2)

    def test_impossible_quiz_and_task_targets_are_excluded(self):
        context = ChallengeEligibilityContext(
            available_task_count=1,
            available_review_task_count=0,
            available_quiz_count=0,
            available_study_day_count=1,
            completable_plan_count=0,
        )
        window = get_period_window(
            ChallengePeriodType.DAILY,
            datetime(2026, 8, 16, 1, 0, tzinfo=UTC),
        )
        selected = select_challenge_templates(
            user_id="user-1",
            window=window,
            templates=CHALLENGE_TEMPLATE_CATALOG,
            context=context,
        )
        selected_keys = {template.key for template in selected}

        self.assertNotIn("daily_complete_2_tasks", selected_keys)
        self.assertNotIn("daily_complete_1_review", selected_keys)
        self.assertNotIn("daily_submit_1_quiz", selected_keys)

    def test_selection_is_deterministic_for_user_and_period(self):
        context = ChallengeEligibilityContext(
            available_task_count=10,
            available_review_task_count=2,
            available_quiz_count=2,
            available_study_day_count=7,
            completable_plan_count=1,
        )
        window = get_period_window(
            ChallengePeriodType.DAILY,
            datetime(2026, 8, 16, 1, 0, tzinfo=UTC),
        )

        first = select_challenge_templates(
            user_id="user-1",
            window=window,
            templates=CHALLENGE_TEMPLATE_CATALOG,
            context=context,
        )
        second = select_challenge_templates(
            user_id="user-1",
            window=window,
            templates=reversed(CHALLENGE_TEMPLATE_CATALOG),
            context=context,
        )

        self.assertEqual(first, second)
        self.assertEqual(len({item.key for item in first}), len(first))

    def test_period_metrics_deduplicate_quizzes_and_tasks(self):
        window = get_period_window(
            ChallengePeriodType.DAILY,
            datetime(2026, 8, 16, 1, 0, tzinfo=UTC),
        )
        task = task_fact("task-1", task_type="review")
        metrics = calculate_period_metrics(
            window,
            [task, task],
            [
                quiz_fact("attempt-1", "quiz-1"),
                quiz_fact("attempt-2", "quiz-1"),
            ],
            [plan_fact("plan-1", frozenset({"learn"}))],
            scheduled_task_ids=["task-1"],
        )

        self.assertEqual(metrics[GamificationMetric.COMPLETED_TASKS], 1)
        self.assertEqual(
            metrics[GamificationMetric.COMPLETED_REVIEW_TASKS],
            1,
        )
        self.assertEqual(metrics[GamificationMetric.DISTINCT_QUIZZES], 1)
        self.assertEqual(metrics[GamificationMetric.STUDY_DAYS], 1)
        self.assertEqual(metrics[GamificationMetric.COMPLETED_PLANS], 1)
        self.assertEqual(
            metrics[GamificationMetric.ALL_SCHEDULED_TASKS_COMPLETED],
            1,
        )

    def test_completed_challenge_remains_claimable_after_period(self):
        period_end = datetime(2026, 8, 16, 15, 0, tzinfo=UTC)
        completed = evaluate_challenge_progress(
            current_status=ChallengeStatus.ACTIVE,
            metric_value=1,
            target_value=1,
            period_end=period_end,
            current_time=datetime(2026, 8, 17, 1, 0, tzinfo=UTC),
        )
        preserved = evaluate_challenge_progress(
            current_status=ChallengeStatus.COMPLETED,
            metric_value=0,
            target_value=1,
            period_end=period_end,
            current_time=datetime(2026, 8, 17, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(completed.status, ChallengeStatus.COMPLETED)
        self.assertTrue(completed.newly_completed)
        self.assertEqual(preserved.status, ChallengeStatus.COMPLETED)
        self.assertEqual(preserved.progress_value, 1)

    def test_incomplete_challenge_expires_at_period_end(self):
        result = evaluate_challenge_progress(
            current_status=ChallengeStatus.ACTIVE,
            metric_value=0,
            target_value=1,
            period_end=datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
            current_time=datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(result.status, ChallengeStatus.EXPIRED)


class GamificationRepositoryTests(unittest.TestCase):
    def test_sync_response_is_validated(self):
        expected = {
            "total_exp": 120,
            "level": 2,
            "current_streak": 3,
            "achievement_exp_awarded": 10,
            "newly_unlocked": [
                {
                    "achievement_key": "first_task_completed",
                    "reward_exp": 10,
                }
            ],
            "newly_completed_challenges": [],
        }
        supabase = FakeSupabase(
            rpc_results={"sync_gamification_state": expected}
        )

        result = sync_gamification_state(supabase)

        self.assertEqual(result, expected)
        self.assertEqual(
            supabase.rpc_calls,
            [("sync_gamification_state", {})],
        )

    def test_claim_sends_only_challenge_id_and_validates_duplicate(self):
        supabase = FakeSupabase(
            rpc_results={
                "claim_gamification_challenge": [
                    {
                        "challenge_id": CHALLENGE_ID,
                        "status": "claimed",
                        "reward_exp": 5,
                        "total_exp": 105,
                        "level": 2,
                        "already_claimed": False,
                    },
                    {
                        "challenge_id": CHALLENGE_ID,
                        "status": "claimed",
                        "reward_exp": 0,
                        "total_exp": 105,
                        "level": 2,
                        "already_claimed": True,
                    },
                ]
            }
        )

        first = claim_challenge_reward(supabase, CHALLENGE_ID)
        second = claim_challenge_reward(supabase, CHALLENGE_ID)

        self.assertEqual(first["reward_exp"], 5)
        self.assertEqual(second["reward_exp"], 0)
        for rpc_name, params in supabase.rpc_calls:
            self.assertEqual(rpc_name, "claim_gamification_challenge")
            self.assertEqual(
                params,
                {"p_challenge_id": str(UUID(CHALLENGE_ID))},
            )

    def test_failed_claim_can_be_retried(self):
        supabase = FakeSupabase(
            rpc_results={
                "claim_gamification_challenge": [
                    RuntimeError("temporary failure"),
                    {
                        "challenge_id": CHALLENGE_ID,
                        "status": "claimed",
                        "reward_exp": 5,
                        "total_exp": 105,
                        "level": 2,
                        "already_claimed": False,
                    },
                ]
            }
        )

        with self.assertRaises(RuntimeError):
            claim_challenge_reward(supabase, CHALLENGE_ID)

        result = claim_challenge_reward(supabase, CHALLENGE_ID)
        self.assertEqual(result["reward_exp"], 5)
        self.assertEqual(len(supabase.rpc_calls), 2)

    def test_owned_reads_always_filter_user_id(self):
        timestamp = "2026-08-16T01:00:00+00:00"
        supabase = FakeSupabase(
            table_results={
                "user_achievements": [
                    {
                        "id": ACHIEVEMENT_ID,
                        "user_id": USER_ID,
                        "achievement_key": "first_task_completed",
                        "progress_value": 1,
                        "unlocked_at": timestamp,
                        "rewarded_at": timestamp,
                        "progress_snapshot": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                ],
                "user_challenges": [
                    {
                        "id": CHALLENGE_ID,
                        "user_id": USER_ID,
                        "template_key": "daily_complete_1_task",
                        "period_type": "daily",
                        "period_start": "2026-08-15T15:00:00+00:00",
                        "period_end": "2026-08-16T15:00:00+00:00",
                        "display_order": 1,
                        "target_value": 1,
                        "progress_value": 1,
                        "reward_exp": 5,
                        "status": "completed",
                        "completed_at": timestamp,
                        "claimed_at": None,
                        "eligibility_snapshot": {},
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                ],
                "user_badge_showcase": [
                    {
                        "user_id": USER_ID,
                        "slot": 1,
                        "achievement_key": "first_task_completed",
                        "equipped_at": timestamp,
                    }
                ],
            }
        )

        self.assertEqual(len(get_user_achievements(supabase, USER_ID)), 1)
        self.assertEqual(len(get_user_challenges(supabase, USER_ID)), 1)
        self.assertEqual(len(get_badge_showcase(supabase, USER_ID)), 1)

        for table_name in (
            "user_achievements",
            "user_challenges",
            "user_badge_showcase",
        ):
            self.assertEqual(
                supabase.table_requests[table_name].filters,
                {"user_id": USER_ID},
            )

    def test_badge_mutations_validate_catalog_and_slots(self):
        timestamp = "2026-08-16T01:00:00+00:00"
        supabase = FakeSupabase(
            rpc_results={
                "equip_gamification_badge": {
                    "user_id": USER_ID,
                    "slot": 2,
                    "achievement_key": "first_task_completed",
                    "equipped_at": timestamp,
                },
                "remove_gamification_badge": {
                    "slot": 2,
                    "removed": True,
                },
            }
        )

        equipped = equip_badge(
            supabase,
            "first_task_completed",
            2,
        )
        removed = remove_badge(supabase, 2)

        self.assertEqual(equipped["slot"], 2)
        self.assertTrue(removed["removed"])
        with self.assertRaises(ValueError):
            equip_badge(supabase, "unknown_achievement", 1)
        with self.assertRaises(ValueError):
            remove_badge(supabase, 4)

    def test_normal_task_completion_uses_atomic_gamification_wrapper(self):
        expected = {
            "task_id": TASK_ID,
            "already_completed": False,
            "task_exp": 10,
            "gamification": gamification_sync_result(),
        }
        supabase = FakeSupabase(
            rpc_results={
                "complete_study_task_with_gamification": expected
            }
        )

        result = complete_study_task(supabase, TASK_ID)

        self.assertEqual(result, expected)
        self.assertEqual(
            supabase.rpc_calls,
            [
                (
                    "complete_study_task_with_gamification",
                    {"p_task_id": TASK_ID},
                )
            ],
        )

    def test_invalid_repository_response_is_rejected(self):
        supabase = FakeSupabase(
            rpc_results={"sync_gamification_state": {"total_exp": -1}}
        )
        with self.assertRaises(RuntimeError):
            sync_gamification_state(supabase)
        with self.assertRaises(ValueError):
            get_user_achievements(supabase, "not-a-uuid")


class GamificationMigrationTests(unittest.TestCase):
    def test_python_and_sql_catalog_rewards_match(self):
        project_root = Path(__file__).resolve().parents[1]
        migration = (
            project_root / "supabase_gamification_actions.sql"
        ).read_text(encoding="utf-8")

        for definition in ACHIEVEMENT_CATALOG:
            expected = (
                f"('{definition.key}', '{definition.metric.value}', "
                f"{definition.target_value}, {definition.reward_exp})"
            )
            self.assertIn(expected, migration)

        for template in CHALLENGE_TEMPLATE_CATALOG:
            expected = (
                f"('{template.key}', '{template.period_type.value}', "
                f"'{template.metric.value}', {template.target_value}, "
                f"{template.reward_exp})"
            )
            self.assertIn(expected, migration)

    def test_migration_enforces_server_reward_boundaries(self):
        project_root = Path(__file__).resolve().parents[1]
        migration = (
            project_root / "supabase_gamification_actions.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("on conflict (user_id, source_key) do nothing", migration)
        self.assertIn("'achievement:' || v_definition.achievement_key", migration)
        self.assertIn("'challenge:' || v_challenge.id::text", migration)
        self.assertIn("'scheduled_task_ids'", migration)
        self.assertIn(
            "revoke execute on function public.complete_study_task(uuid)",
            migration,
        )
        self.assertNotIn("p_reward_exp", migration)


class GamificationSessionStateTests(unittest.TestCase):
    def test_unlock_notifications_are_deduplicated_and_popped_once(self):
        state = {}
        unlock = {
            "achievement_key": "first_task_completed",
            "reward_exp": 10,
        }

        queue_gamification_notifications(
            state,
            {"newly_unlocked": [unlock, unlock]},
        )
        queue_gamification_notifications(
            state,
            {"newly_unlocked": [unlock]},
        )

        self.assertEqual(state[NOTIFICATION_QUEUE_KEY], [unlock])
        self.assertEqual(pop_gamification_notifications(state), [unlock])
        self.assertEqual(pop_gamification_notifications(state), [])

    def test_invalid_unlock_notification_is_ignored(self):
        state = {}

        queue_gamification_notifications(
            state,
            {
                "newly_unlocked": [
                    {"achievement_key": "", "reward_exp": 10},
                    {
                        "achievement_key": "first_task_completed",
                        "reward_exp": 0,
                    },
                ]
            },
        )

        self.assertNotIn(NOTIFICATION_QUEUE_KEY, state)

    def test_challenge_completion_notification_is_deduplicated(self):
        state = {}
        completion = {
            "challenge_id": CHALLENGE_ID,
            "template_key": "daily_complete_1_task",
        }

        queue_gamification_notifications(
            state,
            {"newly_completed_challenges": [completion, completion]},
        )

        self.assertEqual(state[NOTIFICATION_QUEUE_KEY], [completion])

    def test_clear_removes_only_gamification_state(self):
        state = {
            NOTIFICATION_QUEUE_KEY: [{"achievement_key": "first"}],
            "gamification_badge_slot_1": "first_task_completed",
            "tutor_active_session": True,
            "weekly_review_selected_plan": "plan-1",
            "auth_user": "user-1",
        }

        clear_gamification_state(state)

        self.assertEqual(
            state,
            {
                "tutor_active_session": True,
                "weekly_review_selected_plan": "plan-1",
                "auth_user": "user-1",
            },
        )


if __name__ == "__main__":
    unittest.main()
