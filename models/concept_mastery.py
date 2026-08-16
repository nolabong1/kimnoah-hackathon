from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class CourseConceptMasterySummary(ConceptMasterySummary):
    """과목 표시 정보와 취약 판정을 포함한 숙련도입니다."""

    course_name: str = Field(min_length=1, max_length=100)
    is_weak: bool = False


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
    review_stage: int = Field(ge=1, le=3)
    review_interval_days: int = Field(ge=1, le=7)

    @model_validator(mode="after")
    def validate_review_interval(
        self,
    ) -> "AutoReviewTaskSummary":
        """반복 단계별 1·3·7일 목표 간격을 검증합니다."""

        expected_interval = {
            1: 1,
            2: 3,
            3: 7,
        }[self.review_stage]

        if self.review_interval_days != expected_interval:
            raise ValueError(
                "간격 반복 단계와 목표 간격이 일치하지 않습니다."
            )

        return self


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
