from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from models.learning_blueprint import EvidenceKey


ChoiceText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=300,
    ),
]


class QuizQuestionDraft(BaseModel):
    """AI가 생성한 객관식 퀴즈 한 문항입니다."""

    question: str = Field(
        min_length=1,
        max_length=500,
        description="명확하고 독립적으로 이해할 수 있는 문제",
    )
    choices: list[ChoiceText] = Field(
        min_length=4,
        max_length=4,
        description="서로 다른 객관식 선택지 4개",
    )
    correct_answer_index: int = Field(
        ge=0,
        le=3,
        description="정답 선택지의 0부터 시작하는 인덱스",
    )
    explanation: str = Field(
        min_length=1,
        max_length=1000,
        description="정답의 근거를 설명하는 한국어 해설",
    )
    concept_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$",
        description=(
            "대표 개념을 식별하는 영문 소문자 snake_case 키"
        ),
    )
    concept_name: str = Field(
        min_length=1,
        max_length=100,
        description="숙련도를 측정할 대표 개념의 간결한 한국어 이름",
    )
    evidence_key: EvidenceKey = Field(
        description=(
            "공통 학습 설계도의 성공 기준 중 이 문항이 평가하는 한 가지 기준"
        ),
    )

    @field_validator(
        "question",
        "explanation",
        "concept_name",
    )
    @classmethod
    def strip_and_validate_text(
        cls,
        value: str,
    ) -> str:
        """문항 텍스트의 앞뒤 공백을 제거합니다."""

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                "퀴즈 문항 내용은 비어 있을 수 없습니다."
            )

        return cleaned_value

    @field_validator("choices")
    @classmethod
    def strip_and_validate_choices(
        cls,
        choices: list[str],
    ) -> list[str]:
        """선택지를 정리하고 중복 선택지를 거부합니다."""

        cleaned_choices = [
            choice.strip() for choice in choices
        ]

        if any(not choice for choice in cleaned_choices):
            raise ValueError(
                "퀴즈 선택지는 비어 있을 수 없습니다."
            )

        normalized_choices = {
            choice.casefold() for choice in cleaned_choices
        }

        if len(normalized_choices) != len(cleaned_choices):
            raise ValueError(
                "퀴즈 선택지는 서로 달라야 합니다."
            )

        return cleaned_choices


class QuizDraft(BaseModel):
    """AI가 생성한 5문항 객관식 퀴즈입니다."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="과제 주제를 나타내는 간결한 퀴즈 제목",
    )
    questions: list[QuizQuestionDraft] = Field(
        min_length=5,
        max_length=5,
        description="서로 다른 객관식 퀴즈 문항 5개",
    )

    @field_validator("title")
    @classmethod
    def strip_and_validate_title(
        cls,
        value: str,
    ) -> str:
        """제목의 앞뒤 공백을 제거하고 빈 결과를 거부합니다."""

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                "퀴즈 제목은 비어 있을 수 없습니다."
            )

        return cleaned_value

    @field_validator("questions")
    @classmethod
    def validate_unique_questions(
        cls,
        questions: list[QuizQuestionDraft],
    ) -> list[QuizQuestionDraft]:
        """같은 내용의 문항이 반복되는 것을 방지합니다."""

        normalized_questions = {
            question.question.casefold()
            for question in questions
        }

        if len(normalized_questions) != len(questions):
            raise ValueError(
                "퀴즈 문항은 서로 달라야 합니다."
            )

        evidence_counts = {
            "explain": 0,
            "apply": 0,
            "differentiate": 0,
        }
        for question in questions:
            evidence_counts[question.evidence_key] += 1
        if evidence_counts != {
            "explain": 2,
            "apply": 2,
            "differentiate": 1,
        }:
            raise ValueError(
                "퀴즈는 설명 2문항, 적용 2문항, 오해 구분 1문항이어야 합니다."
            )

        return questions
