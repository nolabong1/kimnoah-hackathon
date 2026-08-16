from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


ReviewListItem = Annotated[str, Field(min_length=1, max_length=1000)]
WorkloadAdjustment = Literal["decrease", "maintain", "increase"]


class WeeklyStatisticsSnapshot(BaseModel):
    """주간 회고 생성 시점에 고정해서 저장하는 객관적 통계입니다."""

    plan_title: str = Field(min_length=1, max_length=100)
    course_name: str = Field(min_length=1, max_length=100)
    plan_start_date: date
    plan_target_date: date
    total_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    skipped_tasks: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=100)
    total_planned_minutes: int = Field(ge=0)
    completed_estimated_minutes: int = Field(ge=0)
    scheduled_study_days: int = Field(ge=0)
    days_with_completed_task: int = Field(ge=0)
    completed_by_task_type: dict[str, int]
    completed_estimated_minutes_by_date: dict[str, int]
    task_completion_counts_by_date: dict[str, int]


class WeeklyReviewAnalysis(BaseModel):
    """통계와 사용자 답변을 근거로 생성한 구조화 주간 회고입니다."""

    weekly_summary: str = Field(
        min_length=1,
        max_length=1500,
        description="객관적 기록과 사용자 회고를 구분한 짧은 주간 요약",
    )
    achievements: list[ReviewListItem] = Field(
        max_length=8,
        description="기록 또는 사용자 답변으로 확인되는 구체적인 성취",
    )
    difficulties: list[ReviewListItem] = Field(
        max_length=8,
        description="미완료, 건너뜀 또는 사용자가 언급한 어려움",
    )
    learning_pattern_analysis: str = Field(
        min_length=1,
        max_length=2000,
        description="과제 유형과 예정일별 완료 통계에 근거한 학습 패턴 분석",
    )
    effective_strategies: list[ReviewListItem] = Field(
        max_length=8,
        description="다음 주에도 유지할 가치가 있는 학습 방식",
    )
    improvement_points: list[ReviewListItem] = Field(
        min_length=1,
        max_length=8,
        description="다음 주에 실행할 수 있는 구체적인 개선점",
    )
    recommended_next_goal: str = Field(
        min_length=1,
        max_length=1000,
        description="다음 7일 동안 측정 가능하고 현실적인 추천 목표",
    )
    recommended_strategy: str = Field(
        min_length=1,
        max_length=1500,
        description="다음 주에 적용할 지속 가능한 학습전략",
    )
    recommended_workload_adjustment: WorkloadAdjustment = Field(
        description="학습량을 줄임, 유지, 늘림 중 하나로 조정하는 권고",
    )
    workload_reason: str = Field(
        min_length=1,
        max_length=1000,
        description="완료율과 완료 과제 기준 예상 학습량에 근거한 이유",
    )
    motivation_message: str = Field(
        min_length=1,
        max_length=500,
        description="과장되지 않은 짧은 한국어 응원 메시지",
    )

    @field_validator(
        "weekly_summary",
        "learning_pattern_analysis",
        "recommended_next_goal",
        "recommended_strategy",
        "workload_reason",
        "motivation_message",
    )
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        """문자열 필드의 앞뒤 공백과 빈 응답을 검증합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("주간 회고 내용은 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator(
        "achievements",
        "difficulties",
        "effective_strategies",
        "improvement_points",
    )
    @classmethod
    def strip_list_fields(cls, values: list[str]) -> list[str]:
        """목록 항목의 공백을 정리하고 빈 항목을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("주간 회고 목록에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values
