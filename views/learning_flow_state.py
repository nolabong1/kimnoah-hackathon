from collections.abc import Sequence


TASK_STAGE_OVERVIEW = "overview"
TASK_STAGE_CONTENT = "content"
TASK_STAGE_COMPLETE = "complete"
TASK_FLOW_STAGES = (
    TASK_STAGE_OVERVIEW,
    TASK_STAGE_CONTENT,
    TASK_STAGE_COMPLETE,
)

DASHBOARD_PENDING_TASK_KEY = "dashboard_pending_selected_task_id"


def get_task_stage_key(widget_scope: str, task_id: str) -> str:
    """과제별 학습 단계 위젯 키를 반환합니다."""

    return f"{widget_scope}_task_stage_{task_id}"


def get_task_stage_label(stage: str, task_type: str) -> str:
    """과제 유형에 맞는 단계 라벨을 반환합니다."""

    if stage == TASK_STAGE_OVERVIEW:
        return ":material/assignment: 과제 안내"
    if stage == TASK_STAGE_CONTENT:
        return (
            ":material/quiz: AI 퀴즈"
            if task_type == "quiz"
            else ":material/menu_book: AI 학습자료"
        )
    if stage == TASK_STAGE_COMPLETE:
        return ":material/task_alt: 완료"
    raise ValueError("지원하지 않는 학습 단계입니다.")


def get_default_task_stage(task: dict) -> str:
    """완료 여부를 반영한 과제의 첫 표시 단계를 정합니다."""

    if task.get("status") == "completed":
        return TASK_STAGE_COMPLETE
    return TASK_STAGE_OVERVIEW


def get_next_pending_task_id(
    tasks: Sequence[dict],
    current_task_id: str,
) -> str | None:
    """현재 과제 다음 순서의 미완료 과제를 찾아 한 번 순환합니다."""

    task_ids = [str(task.get("id", "")) for task in tasks]
    try:
        current_index = task_ids.index(str(current_task_id))
    except ValueError:
        current_index = -1

    ordered_candidates = (
        list(tasks[current_index + 1 :]) + list(tasks[:current_index])
        if current_index >= 0
        else list(tasks)
    )
    for task in ordered_candidates:
        task_id = task.get("id")
        if (
            isinstance(task_id, str)
            and task_id
            and task_id != current_task_id
            and task.get("status") != "completed"
        ):
            return task_id
    return None
