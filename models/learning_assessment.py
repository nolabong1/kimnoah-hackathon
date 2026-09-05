import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from models.learning_blueprint import EvidenceKey, LearningDepth
from models.learning_objective import (
    EXPECTED_EVIDENCE_KEYS,
    OBJECTIVE_KEY_PATTERN,
)


AssessmentPhase = Literal["pre", "post"]
AssessmentChoice = Annotated[str, Field(min_length=1, max_length=300)]


def _normalize_question_text(value: str) -> str:
    """문항 중복 비교를 위해 대소문자와 연속 공백을 정규화합니다."""

    return re.sub(r"\s+", " ", value).strip().casefold()


def _percentage_score(correct_count: int, total_questions: int) -> int:
    """PostgreSQL의 양수 반올림과 같은 정수 백분율을 계산합니다."""

    return (correct_count * 100 + total_questions // 2) // total_questions


class LearningAssessmentQuestionDraft(BaseModel):
    """학습목표의 한 성공 기준을 측정하는 객관식 평가 문항입니다."""

    question: str = Field(min_length=1, max_length=500)
    choices: list[AssessmentChoice] = Field(min_length=4, max_length=4)
    correct_answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=1000)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    target_depth: LearningDepth

    @field_validator(
        "question",
        "explanation",
        "objective_key",
        mode="before",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """필수 문자열의 앞뒤 공백을 정리하고 빈 값을 거부합니다."""

        if not isinstance(value, str):
            raise ValueError("평가 문항의 필수 값은 문자열이어야 합니다.")
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("평가 문항의 필수 값은 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator("choices")
    @classmethod
    def validate_choices(cls, choices: list[str]) -> list[str]:
        """선택지를 정리하고 빈 값과 중복 선택지를 거부합니다."""

        cleaned_choices = [choice.strip() for choice in choices]
        if any(not choice for choice in cleaned_choices):
            raise ValueError("평가 선택지는 비어 있을 수 없습니다.")
        normalized_choices = {
            _normalize_question_text(choice) for choice in cleaned_choices
        }
        if len(normalized_choices) != 4:
            raise ValueError("평가 선택지는 서로 달라야 합니다.")
        return cleaned_choices


class LearningAssessmentFormDraft(BaseModel):
    """사전 또는 사후 평가 한 회차의 생성 결과입니다."""

    phase: AssessmentPhase
    title: str = Field(min_length=1, max_length=200)
    questions: list[LearningAssessmentQuestionDraft] = Field(
        min_length=6,
        max_length=15,
    )

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: str) -> str:
        """평가 제목을 정리하고 공백만 있는 값을 거부합니다."""

        if not isinstance(value, str) or not value.strip():
            raise ValueError("평가 제목은 비어 있을 수 없습니다.")
        return value.strip()

    @field_validator("questions")
    @classmethod
    def validate_question_contract(
        cls,
        questions: list[LearningAssessmentQuestionDraft],
    ) -> list[LearningAssessmentQuestionDraft]:
        """목표마다 세 성공 기준이 고정 순서로 한 번씩 출제되게 합니다."""

        normalized_questions = {
            _normalize_question_text(question.question)
            for question in questions
        }
        if len(normalized_questions) != len(questions):
            raise ValueError("평가 문항은 서로 달라야 합니다.")

        objective_keys = list(
            dict.fromkeys(question.objective_key for question in questions)
        )
        if not 2 <= len(objective_keys) <= 5:
            raise ValueError("평가는 2개 이상 5개 이하의 학습목표를 다뤄야 합니다.")

        expected_slots = [
            (objective_key, evidence_key)
            for objective_key in objective_keys
            for evidence_key in EXPECTED_EVIDENCE_KEYS
        ]
        actual_slots = [
            (question.objective_key, question.evidence_key)
            for question in questions
        ]
        if actual_slots != expected_slots:
            raise ValueError(
                "각 학습목표는 explain, apply, differentiate 문항을 "
                "고정 순서로 하나씩 가져야 합니다."
            )

        for objective_key in objective_keys:
            depths = {
                question.target_depth
                for question in questions
                if question.objective_key == objective_key
            }
            if len(depths) != 1:
                raise ValueError(
                    "같은 학습목표의 평가 문항은 목표 깊이가 같아야 합니다."
                )

        return questions

    def measurement_slots(
        self,
    ) -> list[tuple[str, EvidenceKey, LearningDepth]]:
        """사전·사후 평가의 측정 계약을 비교 가능한 순서로 반환합니다."""

        return [
            (
                question.objective_key,
                question.evidence_key,
                question.target_depth,
            )
            for question in self.questions
        ]


class LearningAssessmentPairDraft(BaseModel):
    """동일 측정 계약으로 생성된 사전·사후 평가 한 쌍입니다."""

    pre_assessment: LearningAssessmentFormDraft
    post_assessment: LearningAssessmentFormDraft

    @model_validator(mode="after")
    def validate_parallel_forms(self) -> "LearningAssessmentPairDraft":
        """두 평가의 단계와 목표·성공 기준·깊이 대응을 검증합니다."""

        if self.pre_assessment.phase != "pre":
            raise ValueError("사전 평가의 단계는 pre여야 합니다.")
        if self.post_assessment.phase != "post":
            raise ValueError("사후 평가의 단계는 post여야 합니다.")
        if (
            self.pre_assessment.measurement_slots()
            != self.post_assessment.measurement_slots()
        ):
            raise ValueError(
                "사전·사후 평가는 같은 학습목표, 성공 기준과 깊이를 "
                "같은 순서로 측정해야 합니다."
            )

        pre_questions = {
            _normalize_question_text(question.question)
            for question in self.pre_assessment.questions
        }
        post_questions = {
            _normalize_question_text(question.question)
            for question in self.post_assessment.questions
        }
        if pre_questions & post_questions:
            raise ValueError(
                "사전·사후 평가는 서로 다른 문항으로 구성해야 합니다."
            )
        return self


class GeneratedLearningAssessmentPair(BaseModel):
    """검증된 평가 쌍과 재현 가능한 생성 메타데이터입니다."""

    pair: LearningAssessmentPairDraft
    prompt_version: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)


class LearningAssessmentPairSaveResult(BaseModel):
    """사전·사후 평가 쌍 저장 RPC의 검증된 결과입니다."""

    user_id: UUID
    plan_id: UUID
    pair_key: UUID
    pre_assessment_id: UUID
    post_assessment_id: UUID
    already_processed: bool = False


class LearningAssessmentQuestionView(BaseModel):
    """정답 공개 상태에 따라 제한되는 평가 문항 조회 모델입니다."""

    question: str = Field(min_length=1, max_length=500)
    choices: list[AssessmentChoice] = Field(min_length=4, max_length=4)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    target_depth: LearningDepth
    correct_answer_index: int | None = Field(default=None, ge=0, le=3)
    explanation: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_answer_visibility(self) -> "LearningAssessmentQuestionView":
        """정답 번호와 해설은 함께 공개되거나 함께 숨겨져야 합니다."""

        if (self.correct_answer_index is None) != (self.explanation is None):
            raise ValueError("평가 정답 번호와 해설의 공개 상태가 다릅니다.")
        return self


class LearningAssessmentFormState(BaseModel):
    """조회 RPC가 반환하는 한 평가의 공개 가능한 상태입니다."""

    id: UUID
    phase: AssessmentPhase
    title: str = Field(min_length=1, max_length=200)
    question_count: int = Field(ge=6, le=15)
    objective_snapshot: list[dict] = Field(min_length=2, max_length=5)
    questions: list[LearningAssessmentQuestionView] | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_visible_question_count(self) -> "LearningAssessmentFormState":
        """공개된 문항이 있으면 저장된 문항 수와 일치하게 합니다."""

        if (
            self.questions is not None
            and len(self.questions) != self.question_count
        ):
            raise ValueError("공개된 평가 문항 수가 저장된 문항 수와 다릅니다.")
        return self


class LearningAssessmentObjectiveScore(BaseModel):
    """공식 평가 응시에서 계산된 학습목표별 점수입니다."""

    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    correct_count: int = Field(ge=0, le=3)
    total_questions: Literal[3]
    score: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_score(self) -> "LearningAssessmentObjectiveScore":
        """정답 수와 백분율 점수가 서로 일치하는지 확인합니다."""

        if self.correct_count > self.total_questions:
            raise ValueError("학습목표 정답 수는 전체 문항 수를 넘을 수 없습니다.")
        expected_score = _percentage_score(
            self.correct_count,
            self.total_questions,
        )
        if self.score != expected_score:
            raise ValueError("학습목표 점수가 정답 수와 일치하지 않습니다.")
        return self


class LearningAssessmentQuestionResult(BaseModel):
    """공식 평가의 문항별 서버 채점 결과입니다."""

    question_index: int = Field(ge=0, le=14)
    objective_key: str = Field(
        min_length=1,
        max_length=100,
        pattern=OBJECTIVE_KEY_PATTERN,
    )
    evidence_key: EvidenceKey
    selected_answer_index: int = Field(ge=0, le=3)
    correct_answer_index: int = Field(ge=0, le=3)
    is_correct: bool
    explanation: str = Field(min_length=1, max_length=1000)

    @field_validator("explanation", mode="before")
    @classmethod
    def strip_explanation(cls, value: str) -> str:
        """채점 해설의 앞뒤 공백을 정리합니다."""

        if not isinstance(value, str) or not value.strip():
            raise ValueError("평가 해설은 비어 있을 수 없습니다.")
        return value.strip()

    @model_validator(mode="after")
    def validate_correctness(self) -> "LearningAssessmentQuestionResult":
        """선택 답과 정답으로 계산한 정오답이 저장값과 일치하게 합니다."""

        expected_is_correct = (
            self.selected_answer_index == self.correct_answer_index
        )
        if self.is_correct != expected_is_correct:
            raise ValueError("문항 정오답 결과가 선택 답과 일치하지 않습니다.")
        return self


class LearningAssessmentAttemptResult(BaseModel):
    """공식 사전 또는 사후 평가 제출 RPC의 검증된 결과입니다."""

    attempt_id: UUID
    assessment_id: UUID
    phase: AssessmentPhase
    submission_key: UUID
    correct_count: int = Field(ge=0, le=15)
    total_questions: int = Field(ge=6, le=15)
    score: int = Field(ge=0, le=100)
    objective_scores: list[LearningAssessmentObjectiveScore] = Field(
        min_length=2,
        max_length=5,
    )
    question_results: list[LearningAssessmentQuestionResult] = Field(
        min_length=6,
        max_length=15,
    )
    submitted_at: datetime
    already_processed: bool = False

    @model_validator(mode="after")
    def validate_attempt_totals(self) -> "LearningAssessmentAttemptResult":
        """전체·목표별·문항별 채점 집계가 일관되도록 검증합니다."""

        if self.correct_count > self.total_questions:
            raise ValueError("평가 정답 수는 전체 문항 수를 넘을 수 없습니다.")
        if len(self.question_results) != self.total_questions:
            raise ValueError("문항별 결과 수가 전체 문항 수와 일치하지 않습니다.")
        question_indices = {
            result.question_index for result in self.question_results
        }
        if question_indices != set(range(self.total_questions)):
            raise ValueError("문항별 결과 순서는 0부터 빠짐없이 이어져야 합니다.")
        if sum(result.is_correct for result in self.question_results) != (
            self.correct_count
        ):
            raise ValueError("문항별 정답 수가 평가 정답 수와 일치하지 않습니다.")

        expected_score = _percentage_score(
            self.correct_count,
            self.total_questions,
        )
        if self.score != expected_score:
            raise ValueError("평가 점수가 정답 수와 일치하지 않습니다.")
        if sum(score.total_questions for score in self.objective_scores) != (
            self.total_questions
        ):
            raise ValueError("학습목표별 문항 수 합계가 전체 문항 수와 다릅니다.")
        if sum(score.correct_count for score in self.objective_scores) != (
            self.correct_count
        ):
            raise ValueError("학습목표별 정답 수 합계가 전체 정답 수와 다릅니다.")

        result_objective_keys = {
            result.objective_key for result in self.question_results
        }
        score_objective_keys = {
            score.objective_key for score in self.objective_scores
        }
        if len(score_objective_keys) != len(self.objective_scores):
            raise ValueError("학습목표별 점수의 목표는 서로 달라야 합니다.")
        if result_objective_keys != score_objective_keys:
            raise ValueError("문항 결과와 학습목표별 점수의 목표가 다릅니다.")

        for objective_key in score_objective_keys:
            evidence_keys = [
                result.evidence_key
                for result in self.question_results
                if result.objective_key == objective_key
            ]
            if evidence_keys != EXPECTED_EVIDENCE_KEYS:
                raise ValueError(
                    "학습목표별 문항 결과는 explain, apply, differentiate "
                    "순서여야 합니다."
                )
        return self


class LearningAssessmentPlanState(BaseModel):
    """계획의 사전·사후 평가와 서버 판정 자격을 묶은 상태입니다."""

    user_id: UUID
    plan_id: UUID
    today: date
    task_count: int = Field(ge=0)
    completed_task_count: int = Field(ge=0)
    has_learning_activity: bool
    period_finished: bool
    can_generate: bool
    pre_eligible: bool
    post_eligible: bool
    pre_reason: str | None = None
    post_reason: str | None = None
    pre_assessment: LearningAssessmentFormState | None = None
    post_assessment: LearningAssessmentFormState | None = None
    pre_attempt: LearningAssessmentAttemptResult | None = None
    post_attempt: LearningAssessmentAttemptResult | None = None

    @model_validator(mode="after")
    def validate_state_links(self) -> "LearningAssessmentPlanState":
        """평가와 응시 단계가 계획 상태의 위치와 일치하게 합니다."""

        if self.completed_task_count > self.task_count:
            raise ValueError("완료 과제 수가 전체 과제 수보다 많습니다.")
        for phase, assessment, attempt in (
            ("pre", self.pre_assessment, self.pre_attempt),
            ("post", self.post_assessment, self.post_attempt),
        ):
            if assessment is not None and assessment.phase != phase:
                raise ValueError("평가 단계와 계획 상태의 위치가 다릅니다.")
            if attempt is not None:
                if assessment is None or attempt.assessment_id != assessment.id:
                    raise ValueError("평가 응시와 평가 원본의 연결이 다릅니다.")
                if attempt.phase != phase:
                    raise ValueError("평가 응시 단계가 계획 상태와 다릅니다.")
            if assessment is None:
                continue
            eligible = self.pre_eligible if phase == "pre" else self.post_eligible
            questions = assessment.questions
            if attempt is not None:
                if questions is None or any(
                    question.correct_answer_index is None
                    for question in questions
                ):
                    raise ValueError("완료한 평가의 정답과 해설이 공개되지 않았습니다.")
            elif eligible:
                if questions is None or any(
                    question.correct_answer_index is not None
                    for question in questions
                ):
                    raise ValueError("응시 전 평가의 정답 공개 상태가 올바르지 않습니다.")
            elif questions is not None:
                raise ValueError("응시할 수 없는 평가의 문항이 공개되었습니다.")
        if self.post_eligible and self.pre_attempt is None:
            raise ValueError("사전 진단 없이 사후 평가에 응시할 수 없습니다.")
        return self
