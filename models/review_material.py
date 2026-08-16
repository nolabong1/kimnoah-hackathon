from pydantic import BaseModel, Field, field_validator


class ReviewMaterialDraft(BaseModel):
    """AI가 생성한 학습·복습 자료입니다."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "과제 주제를 명확하게 나타내는 "
            "간결한 학습자료 제목"
        ),
    )

    content_markdown: str = Field(
        min_length=1,
        description=(
            "핵심 요약, 주요 개념, 상세 설명, "
            "학습 예시, 스스로 확인하기를 포함한 "
            "한국어 Markdown 학습자료"
        ),
    )

    @field_validator(
        "title",
        "content_markdown",
    )
    @classmethod
    def strip_and_validate_text(
        cls,
        value: str,
    ) -> str:
        """앞뒤 공백을 제거하고 빈 결과를 거부합니다."""

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                "AI 학습자료 내용은 비어 있을 수 없습니다."
            )

        return cleaned_value


class SourceReviewMaterialDraft(BaseModel):
    """사용자 원본을 바탕으로 생성한 구조화된 복습자료입니다."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="원본의 핵심 주제를 나타내는 간결한 한국어 제목",
    )
    source_overview: str = Field(
        min_length=1,
        description="원본이 다루는 범위와 목적에 대한 간결한 개요",
    )
    core_concepts: list[str] = Field(
        min_length=1,
        max_length=12,
        description="원본에서 확인되는 핵심 개념 목록",
    )
    important_details: list[str] = Field(
        min_length=1,
        max_length=15,
        description="학습자가 기억해야 할 중요한 세부 내용 목록",
    )
    caution_points: list[str] = Field(
        min_length=1,
        max_length=10,
        description="흔한 오해 또는 원본 해석 시 주의할 점 목록",
    )
    self_review_checklist: list[str] = Field(
        min_length=1,
        max_length=10,
        description="학습자가 스스로 확인할 짧은 체크리스트",
    )
    final_summary: str = Field(
        min_length=1,
        description="원본의 핵심을 다시 묶어 주는 최종 요약",
    )

    @field_validator(
        "title",
        "source_overview",
        "final_summary",
    )
    @classmethod
    def strip_source_text_fields(cls, value: str) -> str:
        """구조화 결과의 문자열 필드를 정리합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("복습자료 내용은 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator(
        "core_concepts",
        "important_details",
        "caution_points",
        "self_review_checklist",
    )
    @classmethod
    def strip_source_list_fields(
        cls,
        values: list[str],
    ) -> list[str]:
        """목록 항목의 공백을 제거하고 빈 항목을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("복습자료 목록에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values
