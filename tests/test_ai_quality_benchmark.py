import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models.study_plan import WeeklyStudyPlan
from services.ai_quality_benchmark_service import (
    compare_benchmark_runs,
    load_benchmark_run,
    run_live_benchmark,
    save_benchmark_run,
    select_benchmark_cases,
    validate_live_benchmark_request,
)
from services.ai_quality_service import load_ai_quality_cases
from tools.run_ai_quality_benchmark import main


def _case(case_id: str):
    return next(
        case
        for case in load_ai_quality_cases()
        if case.case_id == case_id
    )


def _valid_python_plan() -> WeeklyStudyPlan:
    return WeeklyStudyPlan.model_validate(
        {
            "title": "Python 반복문 진단 계획",
            "course_name": "Python",
            "level_assessment": "반복문 기초를 적용하는 단계입니다.",
            "weekly_goal": "반복문의 실행 원리를 설명하고 적용합니다.",
            "strategy": "학습 뒤 복습과 퀴즈로 확인합니다.",
            "motivation_message": "매일 한 가지 기준을 확인해보세요.",
            "days": [
                {
                    "day_offset": day_offset,
                    "daily_focus": "반복문 적용",
                    "tasks": [
                        {
                            "title": "반복문 연습",
                            "description": "반복문의 결과를 예상하고 설명합니다.",
                            "task_type": (
                                "review"
                                if day_offset == 4
                                else "quiz"
                                if day_offset == 6
                                else "learn"
                            ),
                            "estimated_minutes": 20,
                        }
                    ],
                }
                for day_offset in range(7)
            ],
        }
    )


class AIQualityBenchmarkTests(unittest.TestCase):
    def test_cases_have_reproducible_generation_inputs(self):
        cases = load_ai_quality_cases()

        for case in cases:
            if case.feature in {"review_material", "quiz"}:
                self.assertIsNotNone(case.benchmark_input.task_title)
                self.assertIsNotNone(case.benchmark_input.task_description)
            if case.feature == "tutor":
                self.assertIsNotNone(case.benchmark_input.question)

    def test_selection_rejects_unknown_duplicate_and_excess_cases(self):
        cases = load_ai_quality_cases()

        with self.assertRaises(ValueError):
            select_benchmark_cases(cases, ["missing_case"])
        with self.assertRaises(ValueError):
            select_benchmark_cases(
                cases,
                [cases[0].case_id, cases[0].case_id],
            )
        with self.assertRaises(ValueError):
            select_benchmark_cases(
                cases,
                [case.case_id for case in cases[:5]],
            )

    def test_paid_run_requires_both_explicit_options(self):
        case_ids = ["study_plan_python_loops_beginner"]

        with self.assertRaises(ValueError):
            validate_live_benchmark_request(
                live=False,
                confirm_paid=True,
                case_ids=case_ids,
            )
        with self.assertRaises(ValueError):
            validate_live_benchmark_request(
                live=True,
                confirm_paid=False,
                case_ids=case_ids,
            )

    def test_cli_listing_never_calls_openai_generation(self):
        with patch(
            "tools.run_ai_quality_benchmark.run_live_benchmark"
        ) as live_run:
            exit_code = main(
                ["--case", "study_plan_python_loops_beginner"]
            )

        self.assertEqual(exit_code, 0)
        live_run.assert_not_called()

    def test_live_plan_run_uses_case_input_and_builds_report(self):
        case = _case("study_plan_python_loops_beginner")

        with (
            patch(
                "services.ai_quality_benchmark_service.generate_weekly_study_plan",
                return_value=_valid_python_plan(),
            ) as generate_plan,
            patch(
                "services.ai_quality_benchmark_service.get_openai_model",
                return_value="benchmark-model",
            ),
        ):
            run = run_live_benchmark([case])

        self.assertEqual(run.model, "benchmark-model")
        self.assertEqual(run.records[0].status, "completed")
        self.assertTrue(run.records[0].report.is_acceptable)
        self.assertTrue(run.records[0].acceptable)
        generate_plan.assert_called_once_with(
            course_name="Python",
            goal=case.learning_goal,
            current_level=2,
            available_schedule={
                f"{day_offset}일차": 45 for day_offset in range(7)
            },
            recent_score=35,
        )

    def test_personalized_case_forwards_repeated_diagnosis_context(self):
        case = _case("review_python_range_boundary")

        with patch(
            "services.ai_quality_benchmark_service.generate_review_material",
            side_effect=RuntimeError("stop after argument capture"),
        ) as generate_review:
            run_live_benchmark([case])

        learner_context = generate_review.call_args.kwargs[
            "learner_context"
        ]
        self.assertIsNotNone(learner_context)
        self.assertEqual(
            learner_context.focus_concepts[0]
            .repeated_diagnoses[0]
            .diagnosis_type,
            "boundary_error",
        )

    def test_failed_generation_stores_only_safe_error_type(self):
        case = _case("study_plan_python_loops_beginner")

        with (
            patch(
                "services.ai_quality_benchmark_service.generate_weekly_study_plan",
                side_effect=RuntimeError("raw provider response"),
            ),
            patch(
                "services.ai_quality_benchmark_service.get_openai_model",
                return_value="benchmark-model",
            ),
        ):
            run = run_live_benchmark([case])

        record = run.records[0]
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_type, "RuntimeError")
        self.assertIsNone(record.output_data)
        self.assertIsNone(record.report)

    def test_snapshot_does_not_overwrite_existing_result(self):
        case = _case("study_plan_python_loops_beginner")
        with (
            patch(
                "services.ai_quality_benchmark_service.generate_weekly_study_plan",
                return_value=_valid_python_plan(),
            ),
            patch(
                "services.ai_quality_benchmark_service.get_openai_model",
                return_value="benchmark-model",
            ),
        ):
            run = run_live_benchmark([case])

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "benchmark.json"
            saved_path = save_benchmark_run(run, output_path)

            self.assertEqual(saved_path, output_path)
            self.assertTrue(output_path.exists())
            loaded_run = load_benchmark_run(output_path)
            self.assertTrue(loaded_run.records[0].acceptable)
            with self.assertRaises(FileExistsError):
                save_benchmark_run(run, output_path)

    def test_comparison_detects_failed_candidate_as_regression(self):
        case = _case("study_plan_python_loops_beginner")
        with (
            patch(
                "services.ai_quality_benchmark_service.generate_weekly_study_plan",
                return_value=_valid_python_plan(),
            ),
            patch(
                "services.ai_quality_benchmark_service.get_openai_model",
                return_value="benchmark-model",
            ),
        ):
            baseline = run_live_benchmark([case])
        with (
            patch(
                "services.ai_quality_benchmark_service.generate_weekly_study_plan",
                side_effect=RuntimeError("provider error"),
            ),
            patch(
                "services.ai_quality_benchmark_service.get_openai_model",
                return_value="benchmark-model",
            ),
        ):
            candidate = run_live_benchmark([case])

        comparisons = compare_benchmark_runs(baseline, candidate)

        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0].outcome, "regressed")


if __name__ == "__main__":
    unittest.main()
