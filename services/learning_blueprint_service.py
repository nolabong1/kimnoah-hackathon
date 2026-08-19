from models.learning_blueprint import (
    LearningBlueprint,
    LearningDepth,
    LearningEvidenceRequirement,
)


EVIDENCE_REQUIREMENTS = (
    (
        "explain",
        "핵심 개념과 적용 조건을 자신의 말로 설명할 수 있다.",
    ),
    (
        "apply",
        "핵심 개념을 구체적인 예시나 문제 상황에 적용할 수 있다.",
    ),
    (
        "differentiate",
        "올바른 적용과 흔한 오해 또는 잘못된 적용을 구분할 수 있다.",
    ),
)


def get_target_depth(current_level: int) -> LearningDepth:
    """기존 1~10 수준을 세 단계의 설명·평가 깊이로 변환합니다."""

    if not 1 <= current_level <= 10:
        raise ValueError("현재 수준은 1부터 10 사이여야 합니다.")
    if current_level <= 3:
        return "foundation"
    if current_level <= 7:
        return "developing"
    return "advanced"


def build_learning_blueprint(
    course_name: str,
    goal: str,
    current_level: int,
    task_title: str,
    task_description: str,
    estimated_minutes: int,
) -> LearningBlueprint:
    """계획과 과제 입력을 공통 학습·평가 계약으로 정규화합니다."""

    cleaned_course_name = course_name.strip()
    cleaned_goal = goal.strip()
    cleaned_task_title = task_title.strip()
    cleaned_task_description = task_description.strip()

    if not cleaned_course_name or len(cleaned_course_name) > 100:
        raise ValueError("과목명은 1자 이상 100자 이하여야 합니다.")
    if not cleaned_goal or len(cleaned_goal) > 1000:
        raise ValueError("학습 목표는 1자 이상 1000자 이하여야 합니다.")
    if not cleaned_task_title or len(cleaned_task_title) > 200:
        raise ValueError("과제명은 1자 이상 200자 이하여야 합니다.")
    if len(cleaned_task_description) > 4000:
        raise ValueError("과제 설명은 4000자 이하여야 합니다.")
    if not 1 <= estimated_minutes <= 1440:
        raise ValueError("예상 학습시간은 1분부터 1440분 사이여야 합니다.")

    return LearningBlueprint(
        course_name=cleaned_course_name,
        primary_objective=cleaned_goal,
        task_focus=cleaned_task_title,
        task_scope=(
            cleaned_task_description
            if cleaned_task_description
            else cleaned_task_title
        ),
        target_depth=get_target_depth(current_level),
        estimated_minutes=estimated_minutes,
        evidence_requirements=[
            LearningEvidenceRequirement(
                key=key,
                description=description,
            )
            for key, description in EVIDENCE_REQUIREMENTS
        ],
    )


def learning_blueprint_to_prompt_payload(
    blueprint: LearningBlueprint,
) -> dict:
    """AI 요청에 필요한 학습 설계도 필드만 직렬화합니다."""

    return blueprint.model_dump(mode="json")
