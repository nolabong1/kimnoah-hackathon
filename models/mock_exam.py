import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from models.learning_blueprint import EvidenceKey
from models.learning_objective import OBJECTIVE_KEY_PATTERN


MockExamDifficulty = Literal["easy", "medium", "hard"]
MockExamChoice = Annotated[str, Field(min_length=1, max_length=300)]


def _normalize_text(value: str) -> str:
    """문항과 선택지 중복 비교를 위한 최소 정규화를 수행합니다."""

    return re.sub(r"\s+", " ", value).strip().casefold()


def _percentage_score(correct_count: int, total_questions: int) -> int:
    """PostgreSQL 양수 반올림과 같은 정수 백분율을 계산합니다."""

    return (correct_count * 100 + total_questions // 2) // total_questions


class MockExamQuestionDraft(BaseModel):
    """AI가 생성하는 시험 대비 모의 평가 문항입니다."""

    question: str = Field(min_length=1, max_length=500)
    choices: list[MockExamChoice] = Field(min_length=4, max_length=4)
    correct_answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=1000)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    difficulty: MockExamDifficulty
    source_title: str | None = Field(default=None, min_length=1, max_length=200)
    source_evidence: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("question", "explanation", "objective_key", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """필수 문자열을 정리하고 공백만 있는 값을 거부합니다."""

        if not isinstance(value, str) or not value.strip():
            raise ValueError("모의 평가 문항의 필수 값은 비어 있을 수 없습니다.")
        return value.strip()

    @field_validator("source_title", "source_evidence", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        """선택적인 원문 근거 문자열을 정리합니다."""

        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("원문 근거는 공백만 포함할 수 없습니다.")
        return value.strip()

    @field_validator("choices")
    @classmethod
    def validate_choices(cls, choices: list[str]) -> list[str]:
        """네 선택지가 모두 비어 있지 않고 서로 다르게 합니다."""

        cleaned = [choice.strip() for choice in choices]
        if any(not choice for choice in cleaned):
            raise ValueError("모의 평가 선택지는 비어 있을 수 없습니다.")
        if len({_normalize_text(choice) for choice in cleaned}) != 4:
            raise ValueError("모의 평가 선택지는 서로 달라야 합니다.")
        return cleaned

    @model_validator(mode="after")
    def validate_source_pair(self) -> "MockExamQuestionDraft":
        """자료명과 원문 근거는 함께 존재하거나 함께 비어 있게 합니다."""

        if (self.source_title is None) != (self.source_evidence is None):
            raise ValueError("모의 평가 자료명과 원문 근거는 함께 제공해야 합니다.")
        return self


class MockExamDraft(BaseModel):
    """계획 전체 범위를 다루는 15문항 모의 평가 생성 결과입니다."""

    title: str = Field(min_length=1, max_length=200)
    recommended_minutes: int = Field(ge=10, le=90)
    questions: list[MockExamQuestionDraft] = Field(min_length=15, max_length=15)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: str) -> str:
        """모의 평가 제목을 정리합니다."""

        if not isinstance(value, str) or not value.strip():
            raise ValueError("모의 평가 제목은 비어 있을 수 없습니다.")
        return value.strip()

    @field_validator("questions")
    @classmethod
    def validate_unique_questions(
        cls,
        questions: list[MockExamQuestionDraft],
    ) -> list[MockExamQuestionDraft]:
        """같은 문제 문장이 반복되지 않게 합니다."""

        if len({_normalize_text(item.question) for item in questions}) != 15:
            raise ValueError("모의 평가 문항은 서로 달라야 합니다.")
        return questions


class GeneratedMockExam(BaseModel):
    """검증된 모의 평가와 생성 재현 메타데이터입니다."""

    exam: MockExamDraft
    prompt_version: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    reference_limited: bool = False


class MockExamSaveResult(BaseModel):
    """모의 평가 저장 RPC 응답입니다."""

    id: UUID
    user_id: UUID
    plan_id: UUID
    generation_key: UUID
    already_processed: bool = False


class MockExamSummary(BaseModel):
    """계획에 저장된 모의 평가의 가벼운 목록 항목입니다."""

    id: UUID
    user_id: UUID
    plan_id: UUID
    title: str = Field(min_length=1, max_length=200)
    question_count: Literal[15]
    recommended_minutes: int = Field(ge=10, le=90)
    attempt_count: int = Field(ge=0)
    best_score: int | None = Field(default=None, ge=0, le=100)
    latest_score: int | None = Field(default=None, ge=0, le=100)
    created_at: datetime


class MockExamQuestionView(BaseModel):
    """정답과 해설을 제거한 응시용 문항입니다."""

    question: str = Field(min_length=1, max_length=500)
    choices: list[MockExamChoice] = Field(min_length=4, max_length=4)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    difficulty: MockExamDifficulty


class MockExamObjectiveScore(BaseModel):
    """한 응시의 학습목표별 서버 채점 결과입니다."""

    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    correct_count: int = Field(ge=0, le=15)
    total_questions: int = Field(ge=1, le=15)
    score: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_score(self) -> "MockExamObjectiveScore":
        """정답 수와 백분율 점수가 일치하게 합니다."""

        if self.correct_count > self.total_questions:
            raise ValueError("학습목표 정답 수는 전체 문항 수를 넘을 수 없습니다.")
        if self.score != _percentage_score(
            self.correct_count,
            self.total_questions,
        ):
            raise ValueError("학습목표 점수가 정답 수와 일치하지 않습니다.")
        return self


class MockExamQuestionResult(BaseModel):
    """모의 평가 문항별 서버 채점 결과입니다."""

    question_index: int = Field(ge=0, le=14)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    difficulty: MockExamDifficulty
    selected_answer_index: int = Field(ge=0, le=3)
    correct_answer_index: int = Field(ge=0, le=3)
    is_correct: bool
    explanation: str = Field(min_length=1, max_length=1000)
    source_title: str | None = Field(default=None, min_length=1, max_length=200)
    source_evidence: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_result(self) -> "MockExamQuestionResult":
        """선택 답과 정답으로 계산한 결과 및 근거 쌍을 검증합니다."""

        if self.is_correct != (
            self.selected_answer_index == self.correct_answer_index
        ):
            raise ValueError("모의 평가 문항의 정오답 결과가 올바르지 않습니다.")
        if (self.source_title is None) != (self.source_evidence is None):
            raise ValueError("모의 평가 자료명과 원문 근거는 함께 제공해야 합니다.")
        return self


class MockExamAttemptResult(BaseModel):
    """한 번의 모의 평가 응시 결과입니다."""

    attempt_id: UUID
    mock_exam_id: UUID
    submission_key: UUID
    attempt_number: int = Field(ge=1)
    correct_count: int = Field(ge=0, le=15)
    total_questions: Literal[15]
    score: int = Field(ge=0, le=100)
    objective_scores: list[MockExamObjectiveScore] = Field(
        min_length=2,
        max_length=5,
    )
    question_results: list[MockExamQuestionResult] = Field(
        min_length=15,
        max_length=15,
    )
    submitted_at: datetime
    already_processed: bool = False

    @model_validator(mode="after")
    def validate_totals(self) -> "MockExamAttemptResult":
        """전체·목표별·문항별 집계가 서로 일치하게 합니다."""

        if self.correct_count > self.total_questions:
            raise ValueError("모의 평가 정답 수가 전체 문항 수를 넘을 수 없습니다.")
        if self.score != _percentage_score(
            self.correct_count,
            self.total_questions,
        ):
            raise ValueError("모의 평가 점수가 정답 수와 일치하지 않습니다.")
        if {item.question_index for item in self.question_results} != set(
            range(15)
        ):
            raise ValueError("모의 평가 문항 결과 순서가 올바르지 않습니다.")
        if sum(item.is_correct for item in self.question_results) != (
            self.correct_count
        ):
            raise ValueError("문항별 정답 수가 전체 정답 수와 다릅니다.")
        if sum(item.total_questions for item in self.objective_scores) != 15:
            raise ValueError("학습목표별 문항 수 합계가 15가 아닙니다.")
        if sum(item.correct_count for item in self.objective_scores) != (
            self.correct_count
        ):
            raise ValueError("학습목표별 정답 수 합계가 전체 결과와 다릅니다.")
        result_keys = {item.objective_key for item in self.question_results}
        score_keys = {item.objective_key for item in self.objective_scores}
        if len(score_keys) != len(self.objective_scores) or result_keys != score_keys:
            raise ValueError("문항 결과와 학습목표별 점수의 목표가 다릅니다.")
        return self


class MockExamAttemptSummary(BaseModel):
    """점수 변화 표시에 필요한 가벼운 응시 요약입니다."""

    attempt_number: int = Field(ge=1)
    correct_count: int = Field(ge=0, le=15)
    score: int = Field(ge=0, le=100)
    submitted_at: datetime


class MockExamState(BaseModel):
    """응시 화면에 필요한 모의 평가와 최신 성적 상태입니다."""

    user_id: UUID
    plan_id: UUID
    exam_id: UUID
    title: str = Field(min_length=1, max_length=200)
    recommended_minutes: int = Field(ge=10, le=90)
    objective_snapshot: list[dict] = Field(min_length=2, max_length=5)
    questions: list[MockExamQuestionView] = Field(min_length=15, max_length=15)
    attempt_count: int = Field(ge=0)
    best_score: int | None = Field(default=None, ge=0, le=100)
    attempt_history: list[MockExamAttemptSummary] = Field(
        default_factory=list,
        max_length=10,
    )
    latest_attempt: MockExamAttemptResult | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_attempt_state(self) -> "MockExamState":
        """응시 횟수와 최신 결과 존재 여부를 일치시킵니다."""

        if (self.attempt_count == 0) != (self.latest_attempt is None):
            raise ValueError("모의 평가 응시 횟수와 최신 결과가 일치하지 않습니다.")
        if (self.attempt_count == 0) != (self.best_score is None):
            raise ValueError("모의 평가 응시 횟수와 최고 점수가 일치하지 않습니다.")
        if bool(self.attempt_history) != (self.attempt_count > 0):
            raise ValueError("모의 평가 응시 횟수와 점수 이력이 일치하지 않습니다.")
        if self.attempt_history and any(
            current.attempt_number >= following.attempt_number
            for current, following in zip(
                self.attempt_history,
                self.attempt_history[1:],
            )
        ):
            raise ValueError("모의 평가 점수 이력 순서가 올바르지 않습니다.")
        if self.latest_attempt is not None:
            if self.latest_attempt.mock_exam_id != self.exam_id:
                raise ValueError("최신 응시가 선택한 모의 평가와 다릅니다.")
            if self.best_score is None or self.best_score < self.latest_attempt.score:
                raise ValueError("모의 평가 최고 점수가 최신 점수보다 낮습니다.")
            if (
                not self.attempt_history
                or self.attempt_history[-1].attempt_number
                != self.latest_attempt.attempt_number
            ):
                raise ValueError("모의 평가 최신 결과와 점수 이력이 다릅니다.")
        return self
