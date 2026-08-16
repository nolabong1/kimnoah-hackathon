from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


ShortText = Annotated[str, Field(min_length=1, max_length=500)]
ReasoningText = Annotated[str, Field(min_length=1, max_length=2000)]
MistakeText = Annotated[str, Field(min_length=1, max_length=1000)]
FeedbackAssessment = Literal[
    "correct",
    "partially_correct",
    "needs_revision",
    "insufficient_information",
]


class TutorHint(BaseModel):
    """정답을 단계적으로 탐색하도록 돕는 단일 힌트입니다."""

    level: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=2500)
    guiding_question: str = Field(min_length=1, max_length=500)

    @field_validator("title", "content", "guiding_question")
    @classmethod
    def strip_hint_text(cls, value: str) -> str:
        """힌트 문자열의 공백을 정리하고 빈 내용을 거부합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("튜터 힌트 내용은 비어 있을 수 없습니다.")
        return cleaned_value


class TutorFinalSolution(BaseModel):
    """사용자가 명시적으로 요청한 뒤에만 보여줄 최종 풀이입니다."""

    final_answer: str = Field(min_length=1, max_length=2000)
    reasoning_steps: list[ReasoningText] = Field(min_length=1, max_length=12)
    why_solution_works: str = Field(min_length=1, max_length=2000)
    common_mistakes: list[MistakeText] = Field(min_length=1, max_length=8)
    self_check_question: str = Field(min_length=1, max_length=500)

    @field_validator(
        "final_answer",
        "why_solution_works",
        "self_check_question",
    )
    @classmethod
    def strip_final_text(cls, value: str) -> str:
        """최종 풀이 문자열을 정리합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("최종 풀이 내용은 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator("reasoning_steps", "common_mistakes")
    @classmethod
    def strip_final_lists(cls, values: list[str]) -> list[str]:
        """최종 풀이 목록의 빈 항목을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("최종 풀이 목록에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values


class TutorGuidance(BaseModel):
    """한 번의 호출로 생성하는 세 단계 힌트와 최종 풀이입니다."""

    problem_summary: str = Field(min_length=1, max_length=1000)
    required_concepts: list[ShortText] = Field(
        min_length=1,
        max_length=12,
    )
    hints: list[TutorHint] = Field(min_length=3, max_length=3)
    final_solution: TutorFinalSolution

    @field_validator("problem_summary")
    @classmethod
    def strip_problem_summary(cls, value: str) -> str:
        """문제 요약의 공백을 정리합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("문제 요약은 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator("required_concepts")
    @classmethod
    def strip_required_concepts(cls, values: list[str]) -> list[str]:
        """필요 개념을 정리하고 중복을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("필요 개념은 비어 있을 수 없습니다.")
        if len({value.casefold() for value in cleaned_values}) != len(
            cleaned_values
        ):
            raise ValueError("필요 개념은 서로 달라야 합니다.")
        return cleaned_values

    @model_validator(mode="after")
    def validate_hint_order(self) -> "TutorGuidance":
        """힌트가 정확히 1, 2, 3 순서인지 확인합니다."""

        if [hint.level for hint in self.hints] != [1, 2, 3]:
            raise ValueError("튜터 힌트 단계는 정확히 1, 2, 3이어야 합니다.")
        return self


class TutorAttemptFeedback(BaseModel):
    """수정한 풀이에 대한 정답 비공개 피드백입니다."""

    assessment: FeedbackAssessment
    what_was_done_well: str = Field(min_length=1, max_length=1500)
    issue: str = Field(min_length=1, max_length=1500)
    next_step: str = Field(min_length=1, max_length=1500)
    recommended_hint_level: int = Field(ge=1, le=3)
    reveals_final_answer: bool

    @field_validator("what_was_done_well", "issue", "next_step")
    @classmethod
    def strip_feedback_text(cls, value: str) -> str:
        """피드백 문자열의 공백을 정리합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("풀이 피드백은 비어 있을 수 없습니다.")
        return cleaned_value

    @model_validator(mode="after")
    def prevent_final_answer_reveal(self) -> "TutorAttemptFeedback":
        """풀이 점검 결과가 최종 정답 공개로 표시되는 것을 거부합니다."""

        if self.reveals_final_answer:
            raise ValueError("풀이 피드백은 최종 정답을 공개할 수 없습니다.")
        return self
