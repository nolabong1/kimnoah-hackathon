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


class SourceGroundedPoint(BaseModel):
    """사용자 원본의 짧은 인용으로 뒷받침되는 복습 항목입니다."""

    content: str = Field(
        min_length=1,
        max_length=700,
        description="원본을 학습하기 쉽게 풀어 쓴 간결한 한국어 설명",
    )
    source_evidence: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "설명을 직접 뒷받침하며 원본에서 그대로 복사한 짧은 구절"
        ),
    )

    @field_validator("content", "source_evidence")
    @classmethod
    def strip_grounded_text(cls, value: str) -> str:
        """근거 항목의 앞뒤 공백을 제거합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("원문 근거 항목은 비어 있을 수 없습니다.")
        return cleaned_value


class SourceRecallQuestion(BaseModel):
    """원본 범위 안에서 답할 수 있는 능동 회상 문제입니다."""

    question: str = Field(
        min_length=1,
        max_length=500,
        description="원본의 핵심 내용을 스스로 떠올리게 하는 짧은 질문",
    )
    answer: str = Field(
        min_length=1,
        max_length=700,
        description="원본 범위 안에서 작성한 간결한 모범 답안",
    )
    source_evidence: str = Field(
        min_length=1,
        max_length=500,
        description="답을 직접 뒷받침하며 원본에서 그대로 복사한 짧은 구절",
    )

    @field_validator("question", "answer", "source_evidence")
    @classmethod
    def strip_recall_text(cls, value: str) -> str:
        """회상 문제 문자열의 앞뒤 공백을 제거합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("회상 문제 내용은 비어 있을 수 없습니다.")
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
    core_concepts: list[SourceGroundedPoint] = Field(
        min_length=1,
        max_length=8,
        description="원문 인용으로 뒷받침되는 핵심 개념 목록",
    )
    important_details: list[SourceGroundedPoint] = Field(
        min_length=1,
        max_length=10,
        description="원문 인용으로 뒷받침되는 중요한 세부 내용 목록",
    )
    caution_points: list[SourceGroundedPoint] = Field(
        max_length=6,
        description="원문 인용으로 뒷받침되는 오해 또는 주의점 목록",
    )
    self_review_checklist: list[str] = Field(
        min_length=1,
        max_length=8,
        description="학습자가 스스로 확인할 짧은 체크리스트",
    )
    active_recall_questions: list[SourceRecallQuestion] = Field(
        min_length=2,
        max_length=5,
        description="정답과 원문 근거를 포함한 짧은 능동 회상 문제",
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
