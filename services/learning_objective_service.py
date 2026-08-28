import hashlib
import json

from models.learning_objective import LearningObjectiveContract


MIN_NEW_PLAN_OBJECTIVES = 2
MAX_PLAN_OBJECTIVES = 5


def learning_objective_to_canonical_payload(
    objective: LearningObjectiveContract,
) -> dict:
    """학습목표 계약을 결정론적인 직렬화 입력으로 변환합니다."""

    return objective.model_dump(mode="json")


def calculate_learning_objective_hash(
    objective: LearningObjectiveContract,
) -> str:
    """동일한 학습목표 계약에 항상 같은 SHA-256 해시를 만듭니다."""

    canonical_json = json.dumps(
        learning_objective_to_canonical_payload(objective),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def validate_new_plan_objective_links(
    objectives: list[LearningObjectiveContract],
    task_objective_keys: list[str],
) -> dict[str, LearningObjectiveContract]:
    """새 계획의 목표 수와 모든 과제 연결을 결정론적으로 검증합니다."""

    if not isinstance(objectives, list) or any(
        not isinstance(objective, LearningObjectiveContract)
        for objective in objectives
    ):
        raise ValueError("학습목표 목록 형식이 올바르지 않습니다.")
    if not MIN_NEW_PLAN_OBJECTIVES <= len(objectives) <= MAX_PLAN_OBJECTIVES:
        raise ValueError(
            "새 학습계획의 학습목표는 2개 이상 5개 이하여야 합니다."
        )

    objective_by_key: dict[str, LearningObjectiveContract] = {}
    for objective in objectives:
        if objective.objective_key in objective_by_key:
            raise ValueError(
                f"학습목표 키가 중복되었습니다: {objective.objective_key}"
            )
        objective_by_key[objective.objective_key] = objective

    if not isinstance(task_objective_keys, list) or not task_objective_keys:
        raise ValueError("학습목표에 연결할 과제가 최소 한 개 필요합니다.")

    normalized_task_keys: list[str] = []
    for objective_key in task_objective_keys:
        if not isinstance(objective_key, str) or not objective_key.strip():
            raise ValueError("모든 과제에는 학습목표 키가 필요합니다.")
        normalized_task_keys.append(objective_key.strip())

    unknown_keys = sorted(
        set(normalized_task_keys) - set(objective_by_key)
    )
    if unknown_keys:
        raise ValueError(
            "과제가 존재하지 않는 학습목표를 참조합니다: "
            + ", ".join(unknown_keys)
        )

    unused_keys = sorted(
        set(objective_by_key) - set(normalized_task_keys)
    )
    if unused_keys:
        raise ValueError(
            "연결된 과제가 없는 학습목표가 있습니다: "
            + ", ".join(unused_keys)
        )

    return objective_by_key
