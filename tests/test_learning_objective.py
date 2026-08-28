import unittest

from pydantic import ValidationError

from models.learning_blueprint import LearningEvidenceRequirement
from models.learning_objective import (
    LearningActivityContext,
    LearningObjectiveContract,
    LinkedLearningBlueprint,
)
from services.learning_objective_service import (
    calculate_learning_objective_hash,
    learning_objective_to_canonical_payload,
    validate_new_plan_objective_links,
)


def _objective(
    objective_key: str = "python_conditionals",
    title: str = "Python 조건문의 실행 흐름",
) -> LearningObjectiveContract:
    return LearningObjectiveContract(
        objective_key=objective_key,
        title=title,
        description="조건식에 따라 실행 분기가 선택되는 원리를 설명하고 적용한다.",
        target_depth="developing",
        evidence_requirements=[
            LearningEvidenceRequirement(
                key="explain",
                description="조건문의 실행 순서를 자신의 말로 설명할 수 있다.",
            ),
            LearningEvidenceRequirement(
                key="apply",
                description="주어진 조건에 맞는 분기 코드를 작성할 수 있다.",
            ),
            LearningEvidenceRequirement(
                key="differentiate",
                description="if와 elif의 역할 차이를 구분할 수 있다.",
            ),
        ],
    )


class LearningObjectiveModelTests(unittest.TestCase):
    def test_contract_strips_outer_whitespace(self):
        objective = _objective(
            objective_key="  python_conditionals  ",
            title="  Python 조건문의 실행 흐름  ",
        )

        self.assertEqual(objective.objective_key, "python_conditionals")
        self.assertEqual(objective.title, "Python 조건문의 실행 흐름")

    def test_contract_rejects_unordered_evidence_requirements(self):
        data = _objective().model_dump()
        data["evidence_requirements"].reverse()

        with self.assertRaisesRegex(
            ValidationError,
            "explain, apply, differentiate",
        ):
            LearningObjectiveContract.model_validate(data)

    def test_contract_rejects_whitespace_only_title(self):
        data = _objective().model_dump()
        data["title"] = "   "

        with self.assertRaisesRegex(ValidationError, "비어 있을 수 없습니다"):
            LearningObjectiveContract.model_validate(data)

    def test_contract_rejects_non_string_title_cleanly(self):
        data = _objective().model_dump()
        data["title"] = 123

        with self.assertRaisesRegex(ValidationError, "문자열이어야 합니다"):
            LearningObjectiveContract.model_validate(data)

    def test_contract_rejects_whitespace_only_evidence_description(self):
        data = _objective().model_dump()
        data["evidence_requirements"][0]["description"] = "   "

        with self.assertRaisesRegex(ValidationError, "성공 기준 설명"):
            LearningObjectiveContract.model_validate(data)

    def test_linked_blueprint_accepts_matching_objective_key(self):
        objective = _objective()
        activity = LearningActivityContext(
            objective_key=objective.objective_key,
            title="조건문 예제 학습",
            description="예제를 읽고 실행 경로를 추적한다.",
            task_type="learn",
            estimated_minutes=25,
        )

        blueprint = LinkedLearningBlueprint(
            objective=objective,
            activity=activity,
        )

        self.assertEqual(
            blueprint.objective.objective_key,
            blueprint.activity.objective_key,
        )

    def test_linked_blueprint_rejects_mismatched_objective_key(self):
        with self.assertRaisesRegex(ValidationError, "일치하지 않습니다"):
            LinkedLearningBlueprint(
                objective=_objective(),
                activity=LearningActivityContext(
                    objective_key="python_loops",
                    title="반복문 예제 학습",
                    task_type="learn",
                    estimated_minutes=20,
                ),
            )


class LearningObjectiveServiceTests(unittest.TestCase):
    def test_hash_is_deterministic_after_model_normalization(self):
        first = _objective(title=" Python 조건문의 실행 흐름 ")
        second = _objective(title="Python 조건문의 실행 흐름")

        self.assertEqual(
            calculate_learning_objective_hash(first),
            calculate_learning_objective_hash(second),
        )
        self.assertEqual(len(calculate_learning_objective_hash(first)), 64)

    def test_canonical_payload_contains_no_runtime_identifiers(self):
        payload = learning_objective_to_canonical_payload(_objective())

        self.assertNotIn("user_id", payload)
        self.assertNotIn("plan_id", payload)
        self.assertNotIn("task_id", payload)

    def test_new_plan_links_accept_two_used_objectives(self):
        objectives = [
            _objective(),
            _objective("python_loops", "Python 반복문"),
        ]

        objective_by_key = validate_new_plan_objective_links(
            objectives,
            ["python_conditionals", "python_loops", "python_loops"],
        )

        self.assertEqual(
            set(objective_by_key),
            {"python_conditionals", "python_loops"},
        )

    def test_new_plan_links_reject_duplicate_objective_keys(self):
        with self.assertRaisesRegex(ValueError, "중복"):
            validate_new_plan_objective_links(
                [_objective(), _objective()],
                ["python_conditionals"],
            )

    def test_new_plan_links_reject_unknown_task_objective(self):
        with self.assertRaisesRegex(ValueError, "존재하지 않는"):
            validate_new_plan_objective_links(
                [
                    _objective(),
                    _objective("python_loops", "Python 반복문"),
                ],
                ["python_conditionals", "python_functions"],
            )

    def test_new_plan_links_reject_unused_objective(self):
        with self.assertRaisesRegex(ValueError, "연결된 과제가 없는"):
            validate_new_plan_objective_links(
                [
                    _objective(),
                    _objective("python_loops", "Python 반복문"),
                ],
                ["python_conditionals"],
            )

    def test_new_plan_links_reject_single_objective(self):
        with self.assertRaisesRegex(ValueError, "2개 이상 5개 이하"):
            validate_new_plan_objective_links(
                [_objective()],
                ["python_conditionals"],
            )


if __name__ == "__main__":
    unittest.main()
