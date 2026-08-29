from supabase import Client

from models.learning_objective import StoredLearningObjective
from services.learning_objective_service import (
    validate_stored_learning_objective,
)


LEARNING_OBJECTIVE_SELECT_FIELDS = (
    "id, user_id, plan_id, objective_key, title, description, "
    "target_depth, evidence_requirements, contract_hash, sort_order, origin"
)


def _normalize_plan_ids(plan_ids: list[str]) -> list[str]:
    """빈 값과 중복을 제거하면서 계획 순서를 보존합니다."""

    return list(
        dict.fromkeys(
            plan_id.strip()
            for plan_id in plan_ids
            if isinstance(plan_id, str) and plan_id.strip()
        )
    )


def get_learning_objectives_by_plan_ids(
    supabase: Client,
    user_id: str,
    plan_ids: list[str],
) -> dict[str, list[StoredLearningObjective]]:
    """본인의 여러 계획에 저장된 학습목표를 한 번에 조회합니다."""

    normalized_plan_ids = _normalize_plan_ids(plan_ids)
    objectives_by_plan = {
        plan_id: [] for plan_id in normalized_plan_ids
    }
    if not normalized_plan_ids:
        return objectives_by_plan

    response = (
        supabase.table("learning_objectives")
        .select(LEARNING_OBJECTIVE_SELECT_FIELDS)
        .eq("user_id", user_id)
        .in_("plan_id", normalized_plan_ids)
        .order("sort_order")
        .execute()
    )

    for objective_data in response.data or []:
        objective = validate_stored_learning_objective(objective_data)
        plan_id = str(objective.plan_id)
        if str(objective.user_id) != user_id or plan_id not in objectives_by_plan:
            raise RuntimeError("학습목표 조회 결과의 소유권이 올바르지 않습니다.")
        objectives_by_plan[plan_id].append(objective)

    return objectives_by_plan


def get_learning_objective_for_task(
    supabase: Client,
    user_id: str,
    plan_id: str,
    task_id: str,
    learning_objective_id: str | None = None,
) -> StoredLearningObjective | None:
    """과제에 연결된 본인 계획의 학습목표를 조회합니다."""

    expected_objective_id = (
        learning_objective_id.strip()
        if isinstance(learning_objective_id, str)
        and learning_objective_id.strip()
        else None
    )
    task_response = (
        supabase.table("study_tasks")
        .select("id, user_id, plan_id, learning_objective_id")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .limit(1)
        .execute()
    )
    if not task_response.data:
        raise RuntimeError("학습목표를 확인할 과제를 찾을 수 없습니다.")
    objective_id = task_response.data[0].get("learning_objective_id")
    if (
        expected_objective_id is not None
        and str(objective_id) != expected_objective_id
    ):
        raise RuntimeError("화면의 과제 학습목표가 최신 DB 연결과 다릅니다.")

    if objective_id is None:
        return None

    response = (
        supabase.table("learning_objectives")
        .select(LEARNING_OBJECTIVE_SELECT_FIELDS)
        .eq("id", str(objective_id))
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise RuntimeError("과제에 연결된 학습목표를 찾을 수 없습니다.")

    objective = validate_stored_learning_objective(response.data[0])
    if str(objective.user_id) != user_id or str(objective.plan_id) != plan_id:
        raise RuntimeError("과제 학습목표의 소유권이 올바르지 않습니다.")
    return objective
