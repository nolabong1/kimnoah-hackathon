from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


LearningDepth = Literal["foundation", "developing", "advanced"]
EvidenceKey = Literal["explain", "apply", "differentiate"]


class LearningEvidenceRequirement(BaseModel):
    """학습목표 달성을 확인할 수 있는 관찰 가능한 성공 기준입니다."""

    key: EvidenceKey
    description: str = Field(min_length=1, max_length=300)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        """성공 기준 설명의 불필요한 공백을 제거합니다."""

        return value.strip()


class LearningBlueprint(BaseModel):
    """학습자료와 퀴즈가 공유하는 최소 학습 설계도입니다."""

    course_name: str = Field(min_length=1, max_length=100)
    primary_objective: str = Field(min_length=1, max_length=1000)
    task_focus: str = Field(min_length=1, max_length=200)
    task_scope: str = Field(min_length=1, max_length=4000)
    target_depth: LearningDepth
    estimated_minutes: int = Field(ge=1, le=1440)
    evidence_requirements: list[LearningEvidenceRequirement] = Field(
        min_length=3,
        max_length=3,
    )

    @field_validator(
        "course_name",
        "primary_objective",
        "task_focus",
        "task_scope",
    )
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        """학습 설계도 문자열의 앞뒤 공백을 정리합니다."""

        return value.strip()

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> "LearningBlueprint":
        """세 성공 기준이 빠짐없이 고정 순서로 존재하는지 확인합니다."""

        evidence_keys = [
            requirement.key
            for requirement in self.evidence_requirements
        ]
        if evidence_keys != ["explain", "apply", "differentiate"]:
            raise ValueError(
                "학습 성공 기준은 explain, apply, differentiate 순서여야 합니다."
            )
        return self
