from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConceptMasterySummary(BaseModel):
    """사용자별 개념 숙련도의 현재 상태입니다."""

    concept_id: UUID
    course_key: str
    concept_key: str
    concept_name: str
    mastery_score: int = Field(ge=0, le=100)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    consecutive_incorrect_count: int = Field(ge=0)
    last_answer_correct: bool | None = None
    last_assessed_at: datetime | None = None


class ConceptMasteryChange(BaseModel):
    """퀴즈 문항 하나로 발생한 숙련도 변경 결과입니다."""

    concept_id: UUID
    concept_key: str
    concept_name: str
    question_index: int = Field(ge=0, le=19)
    is_correct: bool
    score_before: int = Field(ge=0, le=100)
    score_delta: int = Field(ge=-100, le=100)
    score_after: int = Field(ge=0, le=100)
    is_weak: bool


class AutoReviewTaskSummary(BaseModel):
    """취약 개념으로 자동 생성된 복습 과제 정보입니다."""

    task_id: UUID
    plan_id: UUID
    concept_id: UUID
    concept_name: str
    title: str
    scheduled_date: date
    estimated_minutes: int = Field(ge=1, le=1440)


class AdaptiveQuizAnalysis(BaseModel):
    """퀴즈 제출 후 반환할 약점 분석과 자동 재계획 결과입니다."""

    attempt_id: UUID
    mastery_changes: list[ConceptMasteryChange] = Field(
        default_factory=list
    )
    concept_masteries: list[ConceptMasterySummary] = Field(
        default_factory=list
    )
    weak_concepts: list[ConceptMasterySummary] = Field(
        default_factory=list
    )
    auto_review_tasks: list[AutoReviewTaskSummary] = Field(
        default_factory=list
    )
