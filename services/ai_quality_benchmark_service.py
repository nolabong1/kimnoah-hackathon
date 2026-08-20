import json
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from models.ai_quality import (
    AIQualityBenchmarkComparison,
    AIQualityBenchmarkRecord,
    AIQualityBenchmarkRun,
    AIQualityCase,
)
from services.ai_quality_service import (
    evaluate_quiz_quality,
    evaluate_review_material_quality,
    evaluate_study_plan_quality,
    evaluate_tutor_quality,
)
from services.openai_client import get_openai_model
from services.quiz_service import generate_quiz
from services.review_material_service import generate_review_material
from services.study_plan_service import generate_weekly_study_plan
from services.tutor_service import generate_tutor_guidance


MAX_LIVE_BENCHMARK_CASES = 4
DEFAULT_OUTPUT_DIRECTORY = Path(".ai_quality_runs")


def select_benchmark_cases(
    cases: list[AIQualityCase],
    case_ids: list[str],
) -> list[AIQualityCase]:
    """명시적으로 선택한 사례를 요청 순서대로 검증합니다."""

    if not case_ids:
        raise ValueError("실행할 평가 사례를 하나 이상 선택해주세요.")
    if len(case_ids) > MAX_LIVE_BENCHMARK_CASES:
        raise ValueError(
            f"한 번에 최대 {MAX_LIVE_BENCHMARK_CASES}개 사례만 실행할 수 있습니다."
        )
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("같은 평가 사례를 한 번의 실행에 중복 선택할 수 없습니다.")

    case_by_id = {case.case_id: case for case in cases}
    unknown_ids = [case_id for case_id in case_ids if case_id not in case_by_id]
    if unknown_ids:
        raise ValueError(
            "존재하지 않는 평가 사례입니다: " + ", ".join(unknown_ids)
        )
    return [case_by_id[case_id] for case_id in case_ids]


def validate_live_benchmark_request(
    *,
    live: bool,
    confirm_paid: bool,
    case_ids: list[str],
) -> None:
    """실수로 유료 API를 호출하지 않도록 실행 옵션을 검사합니다."""

    if not live:
        raise ValueError("실제 생성은 --live 옵션을 명시해야 실행됩니다.")
    if not confirm_paid:
        raise ValueError("유료 호출 확인을 위해 --confirm-paid 옵션이 필요합니다.")
    if not case_ids:
        raise ValueError("--case 옵션으로 실행할 사례를 선택해주세요.")


def create_benchmark_run_id(
    created_at: datetime | None = None,
) -> str:
    """정렬 가능한 시각과 짧은 난수로 실행 ID를 만듭니다."""

    timestamp = created_at or datetime.now(timezone.utc)
    utc_timestamp = timestamp.astimezone(timezone.utc)
    return f"{utc_timestamp:%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"


def run_live_benchmark(
    cases: list[AIQualityCase],
) -> AIQualityBenchmarkRun:
    """선택 사례를 실제 생성하고 결정론적 평가 결과를 묶습니다."""

    if not 1 <= len(cases) <= MAX_LIVE_BENCHMARK_CASES:
        raise ValueError(
            f"실제 벤치마크는 1~{MAX_LIVE_BENCHMARK_CASES}개 사례만 허용합니다."
        )

    model = get_openai_model()
    created_at = datetime.now(timezone.utc)
    records = [_run_live_case(case) for case in cases]
    return AIQualityBenchmarkRun(
        run_id=create_benchmark_run_id(created_at),
        created_at=created_at,
        model=model,
        records=records,
    )


def save_benchmark_run(
    run: AIQualityBenchmarkRun,
    output_path: Path | None = None,
) -> Path:
    """기존 파일을 덮어쓰지 않고 로컬 JSON 스냅샷을 저장합니다."""

    path = output_path or (
        DEFAULT_OUTPUT_DIRECTORY / f"{run.run_id}.json"
    )
    if path.exists():
        raise FileExistsError(f"기존 벤치마크 파일은 덮어쓸 수 없습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path


def load_benchmark_run(path: Path) -> AIQualityBenchmarkRun:
    """저장된 결과를 Pydantic으로 다시 검증해 불러옵니다."""

    return AIQualityBenchmarkRun.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def compare_benchmark_runs(
    baseline: AIQualityBenchmarkRun,
    candidate: AIQualityBenchmarkRun,
) -> list[AIQualityBenchmarkComparison]:
    """두 실행에 공통으로 존재하는 사례의 회귀 여부를 비교합니다."""

    baseline_by_id = {
        record.case_id: record for record in baseline.records
    }
    candidate_by_id = {
        record.case_id: record for record in candidate.records
    }
    common_case_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
    if not common_case_ids:
        raise ValueError("두 벤치마크 실행에 공통 평가 사례가 없습니다.")

    comparisons = []
    for case_id in common_case_ids:
        baseline_record = baseline_by_id[case_id]
        candidate_record = candidate_by_id[case_id]
        baseline_errors, baseline_warnings = _failed_check_counts(
            baseline_record
        )
        candidate_errors, candidate_warnings = _failed_check_counts(
            candidate_record
        )
        baseline_score = _comparison_score(
            baseline_record,
            baseline_errors,
            baseline_warnings,
        )
        candidate_score = _comparison_score(
            candidate_record,
            candidate_errors,
            candidate_warnings,
        )
        outcome = (
            "improved"
            if candidate_score < baseline_score
            else "regressed"
            if candidate_score > baseline_score
            else "unchanged"
        )
        comparisons.append(
            AIQualityBenchmarkComparison(
                case_id=case_id,
                baseline_status=baseline_record.status,
                candidate_status=candidate_record.status,
                baseline_failed_errors=baseline_errors,
                candidate_failed_errors=candidate_errors,
                baseline_failed_warnings=baseline_warnings,
                candidate_failed_warnings=candidate_warnings,
                outcome=outcome,
            )
        )
    return comparisons


def _run_live_case(case: AIQualityCase) -> AIQualityBenchmarkRecord:
    """한 사례의 생성 실패를 다른 선택 사례와 격리합니다."""

    started_at = monotonic()
    try:
        output, report = _generate_and_evaluate(case)
        return AIQualityBenchmarkRecord(
            case_id=case.case_id,
            feature=case.feature,
            prompt_version=case.prompt_version,
            status="completed",
            duration_ms=round((monotonic() - started_at) * 1000),
            output_data=output.model_dump(mode="json"),
            report=report,
            acceptable=report.is_acceptable,
        )
    except Exception as error:
        return AIQualityBenchmarkRecord(
            case_id=case.case_id,
            feature=case.feature,
            prompt_version=case.prompt_version,
            status="failed",
            duration_ms=round((monotonic() - started_at) * 1000),
            error_type=type(error).__name__,
        )


def _generate_and_evaluate(case: AIQualityCase):
    """평가 기능에 맞는 기존 생성 서비스와 검사기를 연결합니다."""

    benchmark_input = case.benchmark_input
    if case.feature == "study_plan":
        available_schedule = {
            f"{day_offset}일차": benchmark_input.daily_available_minutes
            for day_offset in range(7)
        }
        output = generate_weekly_study_plan(
            course_name=case.course_name,
            goal=case.learning_goal,
            current_level=case.learner_level,
            available_schedule=available_schedule,
            recent_score=benchmark_input.recent_score,
        )
        report = evaluate_study_plan_quality(
            case,
            output,
            available_schedule,
        )
        return output, report

    if case.feature == "review_material":
        output = generate_review_material(
            course_name=case.course_name,
            goal=case.learning_goal,
            current_level=case.learner_level,
            task_title=benchmark_input.task_title or "",
            task_description=benchmark_input.task_description or "",
            task_type="review",
            estimated_minutes=benchmark_input.estimated_minutes,
            learner_context=benchmark_input.learner_context,
        )
        return output, evaluate_review_material_quality(case, output)

    if case.feature == "quiz":
        concept_name = (
            case.expected_terms[0]
            if case.expected_terms
            else case.learning_goal
        )
        existing_concepts = [
            {
                "concept_key": concept_key,
                "concept_name": concept_name,
            }
            for concept_key in case.expected_concept_keys
        ]
        output = generate_quiz(
            course_name=case.course_name,
            goal=case.learning_goal,
            current_level=case.learner_level,
            task_title=benchmark_input.task_title or "",
            task_description=benchmark_input.task_description or "",
            task_type="quiz",
            estimated_minutes=benchmark_input.estimated_minutes,
            existing_concepts=existing_concepts,
            learner_context=benchmark_input.learner_context,
        )
        return output, evaluate_quiz_quality(case, output)

    tutor_result = generate_tutor_guidance(
        course_name=case.course_name,
        goal=case.learning_goal,
        current_level=case.learner_level,
        task_title=benchmark_input.task_title,
        task_description=benchmark_input.task_description,
        reference_title=benchmark_input.reference_title,
        reference_context=benchmark_input.reference_context,
        question=benchmark_input.question or "",
        user_attempt=benchmark_input.user_attempt,
    )
    output = tutor_result.guidance
    return output, evaluate_tutor_quality(case, output)


def _failed_check_counts(
    record: AIQualityBenchmarkRecord,
) -> tuple[int, int]:
    """실패 레코드는 완료 결과보다 낮은 품질로 비교합니다."""

    if record.report is None:
        return 0, 0
    failed_errors = sum(
        not check.passed and check.severity == "error"
        for check in record.report.checks
    )
    failed_warnings = sum(
        not check.passed and check.severity == "warning"
        for check in record.report.checks
    )
    return failed_errors, failed_warnings


def _comparison_score(
    record: AIQualityBenchmarkRecord,
    failed_errors: int,
    failed_warnings: int,
) -> tuple[int, int, int]:
    """실패 상태, 오류, 경고 순으로 회귀 우선순위를 계산합니다."""

    return (
        1 if record.status == "failed" else 0,
        failed_errors,
        failed_warnings,
    )
