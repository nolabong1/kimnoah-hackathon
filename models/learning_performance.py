from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


TaskType = Literal["learn", "review", "quiz"]


class TaskTypePerformance(BaseModel):
    """과제 유형별 계획 수와 완료 수입니다."""

    task_type: TaskType
    total_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)


class QuizPerformance(BaseModel):
    """한 퀴즈의 첫 응시부터 최근 응시까지의 점수 변화입니다."""

    quiz_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    learning_objective_id: str | None = None
    attempt_count: int = Field(ge=0)
    first_score: int | None = Field(default=None, ge=0, le=100)
    latest_score: int | None = Field(default=None, ge=0, le=100)
    best_score: int | None = Field(default=None, ge=0, le=100)
    score_change: int | None = Field(default=None, ge=-100, le=100)
    score_history: list[int] = Field(default_factory=list)


class ConceptPerformance(BaseModel):
    """선택 계획의 퀴즈 문항으로 확인된 개념별 변화입니다."""

    concept_id: str = Field(min_length=1)
    concept_name: str = Field(min_length=1, max_length=100)
    assessed_question_count: int = Field(ge=1)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    first_score_before: int = Field(ge=0, le=100)
    last_score_after: int = Field(ge=0, le=100)
    plan_score_delta: int
    current_score: int | None = Field(default=None, ge=0, le=100)
    current_is_weak: bool | None = None


class ObjectivePerformance(BaseModel):
    """저장된 세부 학습목표 하나의 실행·평가 성과입니다."""

    learning_objective_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    task_count: int = Field(ge=0)
    completed_task_count: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=100)
    quiz_count: int = Field(ge=0)
    attempted_quiz_count: int = Field(ge=0)
    latest_quiz_average: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )


class LearningPerformanceReport(BaseModel):
    """한 학습계획에서 관찰된 실행·퀴즈·숙련도 성과 리포트입니다."""

    plan_id: str = Field(min_length=1)
    plan_title: str = Field(min_length=1, max_length=100)
    course_name: str = Field(min_length=1, max_length=100)
    plan_start_date: date
    plan_target_date: date

    total_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    skipped_tasks: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=100)
    total_planned_minutes: int = Field(ge=0)
    completed_estimated_minutes: int = Field(ge=0)
    task_type_performance: list[TaskTypePerformance]

    quiz_count: int = Field(ge=0)
    attempted_quiz_count: int = Field(ge=0)
    total_quiz_attempts: int = Field(ge=0)
    average_first_score: float | None = Field(default=None, ge=0, le=100)
    average_latest_score: float | None = Field(default=None, ge=0, le=100)
    average_best_score: float | None = Field(default=None, ge=0, le=100)
    average_score_change: float | None = Field(
        default=None,
        ge=-100,
        le=100,
    )

    evaluated_concept_count: int = Field(ge=0)
    improved_concept_count: int = Field(ge=0)
    plan_mastery_score_delta: int
    quizzes: list[QuizPerformance] = Field(default_factory=list)
    concepts: list[ConceptPerformance] = Field(default_factory=list)
    objectives: list[ObjectivePerformance] = Field(default_factory=list)
    unlinked_task_count: int = Field(ge=0)
    unlinked_quiz_count: int = Field(ge=0)
