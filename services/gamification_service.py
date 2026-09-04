from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, time, timedelta
from hashlib import md5
from typing import Any

from models.gamification import (
    AchievementDefinition,
    AchievementProgress,
    ChallengeEligibilityContext,
    ChallengePeriodType,
    ChallengeProgress,
    ChallengeStatus,
    ChallengeTemplate,
    CompletedPlanFact,
    CompletedTaskFact,
    GamificationMetric,
    PeriodWindow,
    QuizSubmissionFact,
)
from services.time_service import SEOUL_TIMEZONE, UTC_TIMEZONE


DAILY_CHALLENGE_LIMIT = 3
WEEKLY_CHALLENGE_LIMIT = 2
BALANCED_TASK_TYPES = frozenset({"learn", "review", "quiz"})


class GamificationValidationError(ValueError):
    """게임화 순수 계산에 사용할 입력이 올바르지 않습니다."""


def get_period_window(
    period_type: ChallengePeriodType,
    current_time: datetime,
) -> PeriodWindow:
    """주입된 시각으로 서울 기준 일간·주간 기간을 계산합니다."""

    _require_aware_datetime(current_time, "현재 시각")
    seoul_now = current_time.astimezone(SEOUL_TIMEZONE)
    local_date = seoul_now.date()

    if period_type == ChallengePeriodType.DAILY:
        start_date = local_date
        end_date = local_date + timedelta(days=1)
    elif period_type == ChallengePeriodType.WEEKLY:
        start_date = local_date - timedelta(days=local_date.weekday())
        end_date = start_date + timedelta(days=7)
    else:
        raise GamificationValidationError(
            "지원하지 않는 도전과제 기간입니다."
        )

    local_start = datetime.combine(
        start_date,
        time.min,
        tzinfo=SEOUL_TIMEZONE,
    )
    local_end = datetime.combine(
        end_date,
        time.min,
        tzinfo=SEOUL_TIMEZONE,
    )
    return PeriodWindow(
        period_type=period_type,
        start_at=local_start.astimezone(UTC_TIMEZONE),
        end_at=local_end.astimezone(UTC_TIMEZONE),
    )


def clamp_progress(progress_value: int, target_value: int) -> int:
    """진행도를 0부터 목표값 사이로 제한합니다."""

    if target_value <= 0:
        raise GamificationValidationError("목표값은 1 이상이어야 합니다.")
    return min(max(progress_value, 0), target_value)


def calculate_achievement_metrics(
    task_facts: Iterable[CompletedTaskFact],
    quiz_facts: Iterable[QuizSubmissionFact],
    plan_facts: Iterable[CompletedPlanFact],
    *,
    longest_streak: int,
) -> dict[GamificationMetric, int]:
    """검증된 학습 사실을 중복 제거해 누적 업적 지표로 집계합니다."""

    if longest_streak < 0:
        raise GamificationValidationError(
            "최장 연속 학습일은 음수일 수 없습니다."
        )

    unique_tasks = _deduplicate_facts(task_facts, "task_id")
    unique_quiz_attempts = _deduplicate_facts(quiz_facts, "attempt_id")
    unique_plans = _deduplicate_facts(plan_facts, "plan_id")

    return {
        GamificationMetric.COMPLETED_TASKS: len(unique_tasks),
        GamificationMetric.LONGEST_STREAK: longest_streak,
        GamificationMetric.COMPLETED_PLANS: len(unique_plans),
        GamificationMetric.COMPLETED_REVIEW_TASKS: sum(
            fact.task_type == "review" for fact in unique_tasks.values()
        ),
        GamificationMetric.QUIZ_SUBMISSIONS: len(unique_quiz_attempts),
        GamificationMetric.PERFECT_QUIZZES: sum(
            fact.is_perfect for fact in unique_quiz_attempts.values()
        ),
        GamificationMetric.BALANCED_COMPLETED_PLANS: sum(
            fact.completed_task_types == BALANCED_TASK_TYPES
            for fact in unique_plans.values()
        ),
    }


def calculate_period_metrics(
    window: PeriodWindow,
    task_facts: Iterable[CompletedTaskFact],
    quiz_facts: Iterable[QuizSubmissionFact],
    plan_facts: Iterable[CompletedPlanFact],
    *,
    scheduled_task_ids: Iterable[str] = (),
) -> dict[GamificationMetric, int]:
    """기간 안의 검증된 행동만으로 도전과제 지표를 집계합니다."""

    period_tasks = _facts_in_window(
        _deduplicate_facts(task_facts, "task_id").values(),
        "completed_at",
        window,
    )
    period_quizzes = _facts_in_window(
        _deduplicate_facts(quiz_facts, "attempt_id").values(),
        "submitted_at",
        window,
    )
    period_plans = _facts_in_window(
        _deduplicate_facts(plan_facts, "plan_id").values(),
        "completed_at",
        window,
    )

    completed_task_ids = {fact.task_id for fact in period_tasks}
    normalized_scheduled_ids = {
        task_id.strip()
        for task_id in scheduled_task_ids
        if isinstance(task_id, str) and task_id.strip()
    }
    study_dates = {
        fact.completed_at.astimezone(SEOUL_TIMEZONE).date()
        for fact in period_tasks
    }
    study_dates.update(
        fact.submitted_at.astimezone(SEOUL_TIMEZONE).date()
        for fact in period_quizzes
    )

    return {
        GamificationMetric.COMPLETED_TASKS: len(completed_task_ids),
        GamificationMetric.COMPLETED_REVIEW_TASKS: sum(
            fact.task_type == "review" for fact in period_tasks
        ),
        GamificationMetric.DISTINCT_QUIZZES: len(
            {fact.quiz_id for fact in period_quizzes}
        ),
        GamificationMetric.STUDY_DAYS: len(study_dates),
        GamificationMetric.COMPLETED_PLANS: len(period_plans),
        GamificationMetric.ALL_SCHEDULED_TASKS_COMPLETED: int(
            bool(normalized_scheduled_ids)
            and normalized_scheduled_ids.issubset(completed_task_ids)
        ),
    }


def evaluate_achievement_progress(
    definition: AchievementDefinition,
    metric_values: Mapping[GamificationMetric, int],
    *,
    previously_unlocked: bool = False,
) -> AchievementProgress:
    """현재 지표로 업적 진행도와 최초 해금 여부를 판정합니다."""

    raw_progress = metric_values.get(definition.metric, 0)
    progress_value = clamp_progress(raw_progress, definition.target_value)
    qualifies_now = raw_progress >= definition.target_value
    is_unlocked = previously_unlocked or qualifies_now

    return AchievementProgress(
        achievement_key=definition.key,
        progress_value=progress_value,
        target_value=definition.target_value,
        is_unlocked=is_unlocked,
        newly_unlocked=qualifies_now and not previously_unlocked,
    )


def evaluate_challenge_progress(
    *,
    current_status: ChallengeStatus,
    metric_value: int,
    target_value: int,
    period_end: datetime,
    current_time: datetime,
) -> ChallengeProgress:
    """완료 보상은 보존하고 미완료 도전과제만 기간 종료 후 만료합니다."""

    _require_aware_datetime(period_end, "기간 종료 시각")
    _require_aware_datetime(current_time, "현재 시각")
    progress_value = clamp_progress(metric_value, target_value)

    if current_status in {
        ChallengeStatus.CLAIMED,
        ChallengeStatus.COMPLETED,
    }:
        return ChallengeProgress(
            progress_value=target_value,
            target_value=target_value,
            status=current_status,
            newly_completed=False,
        )

    if current_status == ChallengeStatus.EXPIRED:
        return ChallengeProgress(
            progress_value=progress_value,
            target_value=target_value,
            status=current_status,
            newly_completed=False,
        )

    if metric_value >= target_value:
        return ChallengeProgress(
            progress_value=target_value,
            target_value=target_value,
            status=ChallengeStatus.COMPLETED,
            newly_completed=True,
        )

    status = (
        ChallengeStatus.EXPIRED
        if current_time >= period_end
        else ChallengeStatus.ACTIVE
    )
    return ChallengeProgress(
        progress_value=progress_value,
        target_value=target_value,
        status=status,
        newly_completed=False,
    )


def is_challenge_template_eligible(
    template: ChallengeTemplate,
    context: ChallengeEligibilityContext,
) -> bool:
    """현재 기간에 달성 가능한 템플릿만 허용합니다."""

    if template.metric == GamificationMetric.COMPLETED_TASKS:
        return context.available_task_count >= template.target_value
    if template.metric == GamificationMetric.COMPLETED_REVIEW_TASKS:
        return context.available_review_task_count >= template.target_value
    if template.metric == GamificationMetric.DISTINCT_QUIZZES:
        return context.available_quiz_count >= template.target_value
    if template.metric == GamificationMetric.STUDY_DAYS:
        return context.available_study_day_count >= template.target_value
    if template.metric == GamificationMetric.COMPLETED_PLANS:
        return context.completable_plan_count >= template.target_value
    if template.metric == GamificationMetric.ALL_SCHEDULED_TASKS_COMPLETED:
        return context.available_task_count > 0
    return False


def select_challenge_templates(
    *,
    user_id: str,
    window: PeriodWindow,
    templates: Iterable[ChallengeTemplate],
    context: ChallengeEligibilityContext,
) -> tuple[ChallengeTemplate, ...]:
    """사용자·기간별 해시 순서로 적격 도전과제를 결정론적으로 선택합니다."""

    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise GamificationValidationError("사용자 ID가 필요합니다.")

    eligible_templates = [
        template
        for template in templates
        if template.period_type == window.period_type
        and is_challenge_template_eligible(template, context)
    ]
    limit = (
        DAILY_CHALLENGE_LIMIT
        if window.period_type == ChallengePeriodType.DAILY
        else WEEKLY_CHALLENGE_LIMIT
    )

    def stable_key(template: ChallengeTemplate) -> tuple[str, str]:
        seed = (
            f"{normalized_user_id}|{window.period_type.value}|"
            f"{window.start_at.astimezone(SEOUL_TIMEZONE).date().isoformat()}|"
            f"{template.key}"
        )
        digest = md5(
            seed.encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        return digest, template.key

    return tuple(sorted(eligible_templates, key=stable_key)[:limit])


def mask_achievement_definition(
    definition: AchievementDefinition,
    *,
    is_unlocked: bool,
) -> dict[str, Any]:
    """잠긴 비밀 업적의 조건과 배지 정보를 노출하지 않습니다."""

    if not definition.hidden or is_unlocked:
        return definition.model_dump(mode="json")

    return {
        "key": definition.key,
        "name_ko": "비밀 업적",
        "description_ko": "조건을 달성하면 공개됩니다.",
        "category": definition.category.value,
        "tier": definition.tier.value,
        "target_value": None,
        "reward_exp": None,
        "badge": {
            "key": None,
            "name_ko": "잠긴 배지",
            "icon": "❔",
            "rarity": None,
        },
        "hidden": True,
    }


def _deduplicate_facts(
    facts: Iterable[Any],
    identifier_field: str,
) -> dict[str, Any]:
    """동일 리소스의 반복 기록을 하나로 세고 충돌 데이터는 거부합니다."""

    unique_facts: dict[str, Any] = {}
    for fact in facts:
        identifier = getattr(fact, identifier_field)
        existing = unique_facts.get(identifier)
        if existing is not None and existing != fact:
            raise GamificationValidationError(
                "같은 학습 기록 ID에 서로 다른 내용이 있습니다."
            )
        unique_facts[identifier] = fact
    return unique_facts


def _facts_in_window(
    facts: Iterable[Any],
    datetime_field: str,
    window: PeriodWindow,
) -> list[Any]:
    """반개구간 안의 시간대 포함 기록만 반환합니다."""

    filtered_facts = []
    for fact in facts:
        occurred_at = getattr(fact, datetime_field)
        _require_aware_datetime(occurred_at, "학습 기록 시각")
        if window.start_at <= occurred_at < window.end_at:
            filtered_facts.append(fact)
    return filtered_facts


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    """서버와 서울 시간 변환에 필요한 시간대 포함 시각을 요구합니다."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise GamificationValidationError(
            f"{field_name}에는 시간대 정보가 필요합니다."
        )
