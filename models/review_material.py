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