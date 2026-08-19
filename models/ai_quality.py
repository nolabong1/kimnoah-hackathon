from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AIQualityFeature = Literal[
    "study_plan",
    "review_material",
    "quiz",
    "tutor",
]
AIQualitySeverity = Literal["error", "warning"]


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
