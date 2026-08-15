from typing import Literal

from pydantic import BaseModel, Field


class StudyTaskDraft(BaseModel):
    """하나의 구체적인 학습 과제입니다."""

    title: str = Field(description="사용자가 바로 실행할 수 있는 구체적인 과제명")
    description: str = Field(description="학습 방법과 완료 기준을 포함한 설명")
    task_type: Literal["learn", "review", "quiz"]
    estimated_minutes: int = Field(description="예상 소요 시간(분)")


class DailyStudyPlan(BaseModel):
    """시작일을 기준으로 한 하루 학습계획입니다."""

    day_offset: int = Field(description="시작일은 0, 마지막 날은 6")
    daily_focus: str = Field(description="그날의 핵심 학습 목표")
    tasks: list[StudyTaskDraft]


class WeeklyStudyPlan(BaseModel):
    """AI가 생성하는 7일 학습계획 전체 구조입니다."""

    title: str
    course_name: str
    level_assessment: str = Field(
        description="사용자가 선택한 10단계 현재 수준을 반영한 짧은 진단"
    )
    weekly_goal: str = Field(description="7일 후 달성해야 할 구체적인 목표")
    strategy: str = Field(description="현재 수준에 맞춘 학습전략")
    days: list[DailyStudyPlan]
    motivation_message: str
