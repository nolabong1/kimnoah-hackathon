from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from models.learner_context import LearnerContext


AIQualityFeature = Literal[
    "study_plan",
    "review_material",
    "quiz",
    "tutor",
]
AIQualitySeverity = Literal["error", "warning"]
AIQualityDimension = Literal[
    "schedule_feasibility",
    "scope_alignment",
    "source_grounding",
    "concept_coverage",
    "misconception_diagnosis",
    "answer_leakage",
    "difficulty_alignment",
    "prompt_injection_resistance",
]


class AIQualityBenchmarkInput(BaseModel):
    """한 평가 사례를 동일한 조건으로 다시 생성하기 위한 입력입니다."""

    daily_available_minutes: int = Field(default=60, ge=1, le=480)
    recent_score: int | None = Field(default=None, ge=0, le=100)
    task_title: str | None = Field(default=None, min_length=1, max_length=200)
    task_description: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    estimated_minutes: int = Field(default=30, ge=1, le=480)
    question: str | None = Field(default=None, min_length=1, max_length=4000)
    user_attempt: str | None = Field(default=None, max_length=4000)
    reference_title: str | None = Field(default=None, min_length=1, max_length=200)
    reference_context: str | None = Field(
        default=None,
        min_length=1,
        max_length=12000,
    )
    learner_context: LearnerContext | None = None

    @field_validator(
        "task_title",
        "task_description",
        "question",
        "user_attempt",
        "reference_title",
        "reference_context",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        """선택 입력이 있으면 앞뒤 공백을 제거합니다."""

        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AIQualityCase(BaseModel):
    """AI 생성 품질을 반복 비교하기 위한 고정 평가 사례입니다."""

    case_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$",
    )
    feature: AIQualityFeature
    prompt_version: str = Field(min_length=1, max_length=100)
    course_name: str = Field(min_length=1, max_length=100)
    learner_level: int = Field(ge=1, le=10)
    learning_goal: str = Field(min_length=1, max_length=1000)
    benchmark_input: AIQualityBenchmarkInput
    quality_dimensions: list[AIQualityDimension] = Field(
        min_length=1,
        max_length=8,
    )
    expected_terms: list[str] = Field(default_factory=list, max_length=20)
    expected_term_groups: list[list[str]] = Field(
        default_factory=list,
        max_length=20,
    )
    forbidden_terms: list[str] = Field(default_factory=list, max_length=20)
    expected_concept_keys: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator(
        "prompt_version",
        "course_name",
        "learning_goal",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        """사례의 핵심 문자열을 정리합니다."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("AI 품질 평가 사례 내용은 비어 있을 수 없습니다.")
        return cleaned

    @field_validator("expected_term_groups")
    @classmethod
    def normalize_term_groups(
        cls,
        groups: list[list[str]],
    ) -> list[list[str]]:
        """같은 의미로 허용할 대안 표현 묶음을 검증합니다."""

        cleaned_groups = []
        for group in groups:
            cleaned = [value.strip() for value in group]
            if not cleaned or any(not value for value in cleaned):
                raise ValueError("AI 품질 대안 용어 묶음은 비어 있을 수 없습니다.")
            if len(cleaned) > 10:
                raise ValueError("AI 품질 대안 용어는 묶음당 10개 이하여야 합니다.")
            if len({value.casefold() for value in cleaned}) != len(cleaned):
                raise ValueError("AI 품질 대안 용어는 중복될 수 없습니다.")
            cleaned_groups.append(cleaned)
        return cleaned_groups

    @field_validator(
        "expected_terms",
        "forbidden_terms",
        "expected_concept_keys",
    )
    @classmethod
    def normalize_term_lists(cls, values: list[str]) -> list[str]:
        """평가 용어의 공백과 중복을 제거합니다."""

        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("AI 품질 평가 용어는 비어 있을 수 없습니다.")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("AI 품질 평가 용어는 중복될 수 없습니다.")
        return cleaned

    @field_validator("quality_dimensions")
    @classmethod
    def validate_unique_quality_dimensions(
        cls,
        values: list[AIQualityDimension],
    ) -> list[AIQualityDimension]:
        """한 사례에서 같은 품질 차원을 중복 선언하지 않습니다."""

        if len(set(values)) != len(values):
            raise ValueError("AI 품질 평가 차원은 중복될 수 없습니다.")
        return values

    @model_validator(mode="after")
    def validate_benchmark_input(self) -> "AIQualityCase":
        """기능별 실제 생성에 필요한 최소 입력을 보장합니다."""

        benchmark_input = self.benchmark_input
        if self.feature in {"review_material", "quiz"} and (
            benchmark_input.task_title is None
            or benchmark_input.task_description is None
        ):
            raise ValueError("학습자료·퀴즈 평가는 과제 제목과 설명이 필요합니다.")
        if self.feature == "tutor" and benchmark_input.question is None:
            raise ValueError("튜터 평가는 재현 가능한 질문이 필요합니다.")
        return self


class AIQualityCheck(BaseModel):
    """한 가지 결정론적 품질 기준의 판정 결과입니다."""

    key: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$",
    )
    passed: bool
    severity: AIQualitySeverity
    message: str = Field(min_length=1, max_length=500)


class AIQualityReport(BaseModel):
    """하나의 평가 사례에 대한 재현 가능한 품질 보고서입니다."""

    case_id: str = Field(min_length=1, max_length=100)
    feature: AIQualityFeature
    prompt_version: str = Field(min_length=1, max_length=100)
    checks: list[AIQualityCheck] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_check_keys(self) -> "AIQualityReport":
        """보고서 안에서 같은 기준을 두 번 기록하지 않습니다."""

        keys = [check.key for check in self.checks]
        if len(set(keys)) != len(keys):
            raise ValueError("AI 품질 검사 키는 서로 달라야 합니다.")
        return self

    @property
    def is_acceptable(self) -> bool:
        """차단 수준 오류가 없으면 자동 검사 통과로 판정합니다."""

        return all(
            check.passed or check.severity != "error"
            for check in self.checks
        )

    @property
    def failed_checks(self) -> list[AIQualityCheck]:
        """실패한 오류와 경고를 표시 순서대로 반환합니다."""

        return [check for check in self.checks if not check.passed]


class AIQualityBenchmarkRecord(BaseModel):
    """한 번의 실제 생성과 결정론적 평가 결과입니다."""

    case_id: str = Field(min_length=1, max_length=100)
    feature: AIQualityFeature
    prompt_version: str = Field(min_length=1, max_length=100)
    status: Literal["completed", "failed"]
    duration_ms: int = Field(ge=0)
    output_data: dict[str, Any] | None = None
    report: AIQualityReport | None = None
    acceptable: bool | None = None
    error_type: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_status_payload(self) -> "AIQualityBenchmarkRecord":
        """성공과 실패 상태에 맞는 결과만 저장합니다."""

        if self.status == "completed":
            if self.output_data is None or self.report is None:
                raise ValueError("완료된 벤치마크에는 출력과 평가 보고서가 필요합니다.")
            if self.error_type is not None:
                raise ValueError("완료된 벤치마크에는 오류 유형을 저장하지 않습니다.")
            expected_acceptable = self.report.is_acceptable
            if self.acceptable is None:
                self.acceptable = expected_acceptable
            elif self.acceptable != expected_acceptable:
                raise ValueError("벤치마크 통과 여부가 평가 보고서와 일치하지 않습니다.")
        elif (
            self.output_data is not None
            or self.report is not None
            or self.acceptable is not None
            or self.error_type is None
        ):
            raise ValueError("실패한 벤치마크에는 오류 유형만 저장합니다.")
        return self


class AIQualityBenchmarkRun(BaseModel):
    """최대 네 개 사례의 선택 실행 결과 스냅샷입니다."""

    run_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}$",
    )
    created_at: datetime
    model: str = Field(min_length=1, max_length=100)
    records: list[AIQualityBenchmarkRecord] = Field(min_length=1, max_length=4)


class AIQualityBenchmarkComparison(BaseModel):
    """같은 사례의 두 실행 사이 품질 검사 변화입니다."""

    case_id: str = Field(min_length=1, max_length=100)
    baseline_status: Literal["completed", "failed"]
    candidate_status: Literal["completed", "failed"]
    baseline_failed_errors: int = Field(ge=0)
    candidate_failed_errors: int = Field(ge=0)
    baseline_failed_warnings: int = Field(ge=0)
    candidate_failed_warnings: int = Field(ge=0)
    outcome: Literal["improved", "unchanged", "regressed"]
