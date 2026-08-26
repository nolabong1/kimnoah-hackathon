from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from models.concept_mastery import CourseConceptMasterySummary
from models.gamification import (
    BadgeShowcaseSlot,
    UserAchievementState,
    UserChallengeState,
)


class DashboardTaskSnapshot(BaseModel):
    """오늘 학습 화면에 필요한 선택 계획의 과제 스냅샷입니다."""

    id: UUID
    scheduled_date: date
    title: str = Field(min_length=1, max_length=200)
    description: str
    task_type: Literal["learn", "review", "quiz"]
    estimated_minutes: int = Field(ge=1, le=1440)
    status: Literal["pending", "completed", "skipped"]
    source_type: Literal["weekly_plan", "weakness_review"]
    concept_id: UUID | None = None
    review_stage: int | None = Field(default=None, ge=1, le=3)
    review_interval_days: int | None = Field(default=None, ge=1, le=7)

    @model_validator(mode="after")
    def validate_review_metadata(self) -> "DashboardTaskSnapshot":
        """일반 과제와 간격 반복 과제의 표시 메타데이터를 검증합니다."""

        if self.source_type == "weekly_plan":
            if self.review_stage is not None or self.review_interval_days is not None:
                raise ValueError("일반 과제에는 반복 복습 단계가 없어야 합니다.")
            return self

        expected_interval = {1: 1, 2: 3, 3: 7}.get(self.review_stage)
        if expected_interval is None or self.review_interval_days != expected_interval:
            raise ValueError("자동 복습 과제의 반복 단계와 간격이 일치하지 않습니다.")
        if self.concept_id is None:
            raise ValueError("자동 복습 과제에는 연결 개념이 필요합니다.")
        return self


class DashboardSnapshot(BaseModel):
    """선택 계획의 오늘 학습 화면을 한 번에 구성하는 읽기 전용 응답입니다."""

    user_id: UUID
    plan_id: UUID
    plan_tasks: list[DashboardTaskSnapshot] = Field(default_factory=list)
    concept_masteries: list[CourseConceptMasterySummary] = Field(
        default_factory=list
    )
    achievements: list[UserAchievementState] = Field(default_factory=list)
    challenges: list[UserChallengeState] = Field(default_factory=list)
    badge_showcase: list[BadgeShowcaseSlot] = Field(default_factory=list)
