from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from models.learning_blueprint import (
    LearningDepth,
    LearningEvidenceRequirement,
)


TaskType = Literal["learn", "review", "quiz"]
OBJECTIVE_KEY_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
EXPECTED_EVIDENCE_KEYS = ["explain", "apply", "differentiate"]


def _strip_required_text(value: str, field_name: str) -> str:
    """필수 문자열을 정리하고 공백만 있는 값을 거부합니다."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name}은 문자열이어야 합니다.")
    cleaned_value = value.strip()
    if not cleaned_value:
        raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
    return cleaned_value


class LearningObjectiveContract(BaseModel):
    """여러 학습 과제와 자료·퀴즈가 공유하는 학습목표 계약입니다."""

    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    target_depth: LearningDepth
    evidence_requirements: list[LearningEvidenceRequirement] = Field(
        min_length=3,
        max_length=3,
    )

    @field_validator("objective_key", mode="before")
    @classmethod
    def strip_objective_key(cls, value: str) -> str:
        """목표 키의 앞뒤 공백을 제거합니다."""

        return _strip_required_text(value, "학습목표 키")

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        """목표 문자열의 앞뒤 공백을 정리합니다."""

        return _strip_required_text(value, "학습목표 제목과 설명")

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> "LearningObjectiveContract":
        """성공 기준이 빠짐없이 고정 순서로 존재하는지 확인합니다."""

        evidence_keys = [
            requirement.key
            for requirement in self.evidence_requirements
        ]
        if evidence_keys != EXPECTED_EVIDENCE_KEYS:
            raise ValueError(
                "학습목표 성공 기준은 explain, apply, differentiate "
                "순서여야 합니다."
            )
        if any(
            not requirement.description.strip()
            for requirement in self.evidence_requirements
        ):
            raise ValueError("학습목표 성공 기준 설명은 비어 있을 수 없습니다.")
        return self


class LearningActivityContext(BaseModel):
    """공통 학습목표를 수행하는 개별 과제의 실행 문맥입니다."""

    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    task_type: TaskType
    estimated_minutes: int = Field(ge=1, le=1440)

    @field_validator("objective_key", mode="before")
    @classmethod
    def strip_objective_key(cls, value: str) -> str:
        """과제에 연결된 목표 키의 앞뒤 공백을 제거합니다."""

        return _strip_required_text(value, "학습목표 키")

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: str) -> str:
        """과제 제목을 정리하고 빈 값을 거부합니다."""

        return _strip_required_text(value, "과제 제목")

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: str) -> str:
        """선택적인 과제 설명의 앞뒤 공백을 정리합니다."""

        if not isinstance(value, str):
            raise ValueError("과제 설명은 문자열이어야 합니다.")
        return value.strip()


class LinkedLearningBlueprint(BaseModel):
    """공통 목표 계약과 목표를 수행할 개별 과제를 함께 보존합니다."""

    objective: LearningObjectiveContract
    activity: LearningActivityContext

    @model_validator(mode="after")
    def validate_objective_link(self) -> "LinkedLearningBlueprint":
        """과제가 다른 학습목표 계약에 잘못 연결되는 것을 막습니다."""

        if self.objective.objective_key != self.activity.objective_key:
            raise ValueError(
                "과제의 학습목표 키가 학습목표 계약과 일치하지 않습니다."
            )
        return self


class StoredLearningObjective(LearningObjectiveContract):
    """Supabase에 저장된 사용자·계획 소유 학습목표입니다."""

    id: UUID
    user_id: UUID
    plan_id: UUID
    contract_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    sort_order: int = Field(ge=1, le=5)
    origin: Literal["generated", "legacy_backfill"]

    @model_validator(mode="after")
    def validate_hash_origin(self) -> "StoredLearningObjective":
        """생성 목표만 결정론적 계약 해시를 가지게 합니다."""

        if self.origin == "generated" and self.contract_hash is None:
            raise ValueError("생성 학습목표에는 계약 해시가 필요합니다.")
        if self.origin == "legacy_backfill" and self.contract_hash is not None:
            raise ValueError("기존 계획 호환 목표에는 계약 해시를 만들지 않습니다.")
        return self


class LearningObjectiveConnectionSummary(BaseModel):
    """학습목표 하나에 실제로 연결된 학습 활동의 읽기 전용 요약입니다."""

    objective: StoredLearningObjective
    task_titles: list[str] = Field(default_factory=list)
    source_material_titles: list[str] = Field(default_factory=list)
    review_material_titles: list[str] = Field(default_factory=list)
    quiz_titles: list[str] = Field(default_factory=list)


class LearningObjectiveConnectionReport(BaseModel):
    """계획의 목표별 연결과 이전 버전 미연결 행 개수를 함께 보존합니다."""

    summaries: list[LearningObjectiveConnectionSummary] = Field(
        default_factory=list
    )
    unlinked_task_count: int = Field(default=0, ge=0)
    unlinked_source_material_count: int = Field(default=0, ge=0)
    unlinked_review_material_count: int = Field(default=0, ge=0)
    unlinked_quiz_count: int = Field(default=0, ge=0)
