from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AchievementCategory(StrEnum):
    """업적을 분류하는 고정 카테고리입니다."""

    TASK = "task"
    STREAK = "streak"
    PLAN = "plan"
    REVIEW = "review"
    QUIZ = "quiz"
    BALANCE = "balance"


class AchievementTier(StrEnum):
    """업적의 단계 표시값입니다."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class BadgeRarity(StrEnum):
    """배지 희귀도 표시값입니다."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class ChallengePeriodType(StrEnum):
    """도전과제의 반복 기간입니다."""

    DAILY = "daily"
    WEEKLY = "weekly"


class ChallengeStatus(StrEnum):
    """저장된 사용자 도전과제의 상태입니다."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CLAIMED = "claimed"
    EXPIRED = "expired"


class ChallengeDifficulty(StrEnum):
    """도전과제의 체감 난이도입니다."""

    EASY = "easy"
    NORMAL = "normal"
    CHALLENGING = "challenging"


class GamificationMetric(StrEnum):
    """신뢰할 수 있는 학습 기록에서 계산할 지표입니다."""

    COMPLETED_TASKS = "completed_tasks"
    LONGEST_STREAK = "longest_streak"
    COMPLETED_PLANS = "completed_plans"
    COMPLETED_REVIEW_TASKS = "completed_review_tasks"
    QUIZ_SUBMISSIONS = "quiz_submissions"
    PERFECT_QUIZZES = "perfect_quizzes"
    BALANCED_COMPLETED_PLANS = "balanced_completed_plans"
    DISTINCT_QUIZZES = "distinct_quizzes"
    STUDY_DAYS = "study_days"
    ALL_SCHEDULED_TASKS_COMPLETED = "all_scheduled_tasks_completed"


class BadgeDefinition(BaseModel, frozen=True):
    """업적 하나에 대응하는 정적 배지 정의입니다."""

    key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    name_ko: str = Field(min_length=1, max_length=100)
    icon: str = Field(min_length=1, max_length=20)
    rarity: BadgeRarity


class AchievementDefinition(BaseModel, frozen=True):
    """버전 관리되는 업적 카탈로그 항목입니다."""

    key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    series_key: str = Field(
        pattern=r"^[a-z0-9_]+$",
        min_length=1,
        max_length=100,
    )
    name_ko: str = Field(min_length=1, max_length=100)
    description_ko: str = Field(min_length=1, max_length=300)
    category: AchievementCategory
    tier: AchievementTier
    metric: GamificationMetric
    target_value: int = Field(gt=0)
    reward_exp: int = Field(gt=0)
    sort_order: int = Field(gt=0)
    badge: BadgeDefinition
    hidden: bool = False


class ChallengeTemplate(BaseModel, frozen=True):
    """일간 또는 주간 도전과제의 정적 템플릿입니다."""

    key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=100)
    name_ko: str = Field(min_length=1, max_length=100)
    description_ko: str = Field(min_length=1, max_length=300)
    period_type: ChallengePeriodType
    difficulty: ChallengeDifficulty
    metric: GamificationMetric
    target_value: int = Field(gt=0)
    reward_exp: int = Field(gt=0)
    sort_order: int = Field(gt=0)


class ChallengeEligibilityContext(BaseModel, frozen=True):
    """현재 기간에 실제로 수행 가능한 학습량 요약입니다."""

    available_task_count: int = Field(default=0, ge=0)
    available_review_task_count: int = Field(default=0, ge=0)
    available_quiz_count: int = Field(default=0, ge=0)
    available_study_day_count: int = Field(default=0, ge=0)
    completable_plan_count: int = Field(default=0, ge=0)


class AchievementProgress(BaseModel, frozen=True):
    """현재 지표를 업적 하나에 적용한 순수 판정 결과입니다."""

    achievement_key: str
    progress_value: int = Field(ge=0)
    target_value: int = Field(gt=0)
    is_unlocked: bool
    newly_unlocked: bool


class ChallengeProgress(BaseModel, frozen=True):
    """기간 지표를 저장된 도전과제에 적용한 순수 판정 결과입니다."""

    progress_value: int = Field(ge=0)
    target_value: int = Field(gt=0)
    status: ChallengeStatus
    newly_completed: bool


class PeriodWindow(BaseModel, frozen=True):
    """서울 시간 기준으로 계산한 반개구간 [시작, 종료)입니다."""

    period_type: ChallengePeriodType
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def validate_period(self) -> "PeriodWindow":
        """시간대와 기간 순서를 검증합니다."""

        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("도전과제 기간에는 시간대 정보가 필요합니다.")
        if self.end_at <= self.start_at:
            raise ValueError("도전과제 종료 시각은 시작 시각보다 늦어야 합니다.")
        return self


class CompletedTaskFact(BaseModel, frozen=True):
    """EXP 원장으로 검증된 과제 완료 사실입니다."""

    task_id: str = Field(min_length=1, max_length=100)
    task_type: str = Field(pattern=r"^(learn|review|quiz)$")
    completed_at: datetime


class QuizSubmissionFact(BaseModel, frozen=True):
    """서버 제출 RPC로 검증된 퀴즈 응시 사실입니다."""

    attempt_id: str = Field(min_length=1, max_length=100)
    quiz_id: str = Field(min_length=1, max_length=100)
    submitted_at: datetime
    is_perfect: bool = False


class CompletedPlanFact(BaseModel, frozen=True):
    """하나 이상의 검증된 완료 과제를 가진 완료 계획입니다."""

    plan_id: str = Field(min_length=1, max_length=100)
    completed_task_types: frozenset[str] = Field(min_length=1)
    completed_at: datetime

    @model_validator(mode="after")
    def validate_task_types(self) -> "CompletedPlanFact":
        """계획 완료 사실에 알려진 과제 유형만 허용합니다."""

        allowed_types = {"learn", "review", "quiz"}
        if not self.completed_task_types.issubset(allowed_types):
            raise ValueError("완료 계획의 과제 유형이 올바르지 않습니다.")
        return self


class AchievementUnlockSummary(BaseModel):
    """한 번의 동기화에서 새로 해금된 업적과 지급 보상입니다."""

    achievement_key: str = Field(min_length=1, max_length=100)
    reward_exp: int = Field(gt=0)


class ChallengeCompletionSummary(BaseModel):
    """한 번의 동기화에서 새로 완료된 도전과제입니다."""

    challenge_id: UUID
    template_key: str = Field(min_length=1, max_length=100)


class GamificationSyncResult(BaseModel):
    """서버의 원자적 게임화 동기화 결과입니다."""

    total_exp: int = Field(ge=0)
    level: int = Field(ge=1)
    current_streak: int = Field(ge=0)
    achievement_exp_awarded: int = Field(ge=0)
    newly_unlocked: list[AchievementUnlockSummary] = Field(
        default_factory=list
    )
    newly_completed_challenges: list[ChallengeCompletionSummary] = Field(
        default_factory=list
    )


class ChallengeClaimResult(BaseModel):
    """명시적 도전과제 보상 수령 결과입니다."""

    challenge_id: UUID
    status: ChallengeStatus
    reward_exp: int = Field(ge=0)
    total_exp: int = Field(ge=0)
    level: int = Field(ge=1)
    already_claimed: bool

    @model_validator(mode="after")
    def validate_claimed_status(self) -> "ChallengeClaimResult":
        """보상 수령 응답은 항상 claimed 상태여야 합니다."""

        if self.status != ChallengeStatus.CLAIMED:
            raise ValueError("보상 수령 결과 상태가 올바르지 않습니다.")
        if self.already_claimed and self.reward_exp != 0:
            raise ValueError("이미 수령한 보상은 다시 지급할 수 없습니다.")
        return self


class UserAchievementState(BaseModel):
    """사용자별 업적 진행·해금 저장 상태입니다."""

    id: UUID
    user_id: UUID
    achievement_key: str = Field(min_length=1, max_length=100)
    progress_value: int = Field(ge=0)
    unlocked_at: datetime | None = None
    rewarded_at: datetime | None = None
    progress_snapshot: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UserChallengeState(BaseModel):
    """사용자에게 고정 배정된 일간·주간 도전과제 상태입니다."""

    id: UUID
    user_id: UUID
    template_key: str = Field(min_length=1, max_length=100)
    period_type: ChallengePeriodType
    period_start: datetime
    period_end: datetime
    display_order: int = Field(ge=1, le=3)
    target_value: int = Field(gt=0)
    progress_value: int = Field(ge=0)
    reward_exp: int = Field(gt=0)
    status: ChallengeStatus
    completed_at: datetime | None = None
    claimed_at: datetime | None = None
    eligibility_snapshot: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_period_order(self) -> "UserChallengeState":
        """기간과 표시 순서가 저장 규칙을 만족하는지 검증합니다."""

        max_order = 3 if self.period_type == ChallengePeriodType.DAILY else 2
        if self.display_order > max_order:
            raise ValueError("도전과제 표시 순서가 올바르지 않습니다.")
        if self.period_end <= self.period_start:
            raise ValueError("도전과제 기간이 올바르지 않습니다.")
        if self.progress_value > self.target_value:
            raise ValueError("도전과제 진행도가 목표를 초과했습니다.")
        return self


class BadgeShowcaseSlot(BaseModel):
    """사용자가 대표로 장착한 해금 배지 슬롯입니다."""

    user_id: UUID
    slot: int = Field(ge=1, le=3)
    achievement_key: str = Field(min_length=1, max_length=100)
    equipped_at: datetime
