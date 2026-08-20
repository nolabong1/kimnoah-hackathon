from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RecentAssessmentResult = Literal["correct", "incorrect", "unknown"]
MisconceptionDiagnosisType = Literal[
    "concept_confusion",
    "condition_omission",
    "procedure_error",
    "calculation_error",
    "boundary_error",
    "overgeneralization",
    "representation_error",
    "other",
]

MISCONCEPTION_DIAGNOSIS_TYPES: tuple[
    MisconceptionDiagnosisType,
    ...,
] = (
    "concept_confusion",
    "condition_omission",
    "procedure_error",
    "calculation_error",
    "boundary_error",
    "overgeneralization",
    "representation_error",
    "other",
)


class LearnerDiagnosisSignal(BaseModel):
    """반복해서 관찰된 개념별 오답 유형 신호입니다."""

    diagnosis_type: MisconceptionDiagnosisType
    occurrence_count: int = Field(ge=2, le=5)


class LearnerConceptContext(BaseModel):
    """AI 개인화에 필요한 한 개념의 최소 숙련도 신호입니다."""

    concept_key: str = Field(min_length=1, max_length=100)
    concept_name: str = Field(min_length=1, max_length=100)
    mastery_score: int = Field(ge=0, le=100)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    consecutive_incorrect_count: int = Field(ge=0)
    recent_result: RecentAssessmentResult
    is_weak: bool
    repeated_diagnoses: list[LearnerDiagnosisSignal] = Field(
        default_factory=list,
        max_length=2,
    )

    @field_validator("concept_key", "concept_name")
    @classmethod
    def strip_concept_text(cls, value: str) -> str:
        """개념 식별 문자열의 공백을 정리합니다."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("학습자 문맥의 개념 정보는 비어 있을 수 없습니다.")
        return cleaned


class LearnerContext(BaseModel):
    """AI 생성기에 전달할 제한된 과목별 학습자 상태입니다."""

    course_key: str = Field(min_length=1, max_length=120)
    evaluated_concept_count: int = Field(ge=1)
    weak_concept_count: int = Field(ge=0)
    average_mastery_score: float = Field(ge=0, le=100)
    focus_concepts: list[LearnerConceptContext] = Field(
        default_factory=list,
        max_length=6,
    )
    stable_concepts: list[LearnerConceptContext] = Field(
        default_factory=list,
        max_length=3,
    )

    @field_validator("course_key")
    @classmethod
    def strip_course_key(cls, value: str) -> str:
        """과목 키의 불필요한 공백을 제거합니다."""

        return value.strip()

    @model_validator(mode="after")
    def validate_summary_counts(self) -> "LearnerContext":
        """요약 개수와 전달된 개념 목록의 기본 일관성을 검사합니다."""

        if self.weak_concept_count > self.evaluated_concept_count:
            raise ValueError("취약 개념 수가 평가된 개념 수보다 많습니다.")
        focus_keys = {concept.concept_key for concept in self.focus_concepts}
        stable_keys = {concept.concept_key for concept in self.stable_concepts}
        if len(focus_keys) != len(self.focus_concepts):
            raise ValueError("우선 학습 개념은 중복될 수 없습니다.")
        if len(stable_keys) != len(self.stable_concepts):
            raise ValueError("안정 개념은 중복될 수 없습니다.")
        if focus_keys & stable_keys:
            raise ValueError("같은 개념을 우선 개념과 안정 개념에 함께 넣을 수 없습니다.")
        return self
