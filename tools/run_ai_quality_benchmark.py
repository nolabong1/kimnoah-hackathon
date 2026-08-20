import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.ai_quality_benchmark_service import (  # noqa: E402
    MAX_LIVE_BENCHMARK_CASES,
    compare_benchmark_runs,
    load_benchmark_run,
    run_live_benchmark,
    save_benchmark_run,
    select_benchmark_cases,
    validate_live_benchmark_request,
)
from services.ai_quality_service import load_ai_quality_cases  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "버전 관리된 AI 품질 사례를 조회하거나 선택적으로 실제 생성합니다."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        dest="case_ids",
        help=(
            "실행할 case_id입니다. 여러 번 지정할 수 있으며 "
            f"최대 {MAX_LIVE_BENCHMARK_CASES}개입니다."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="선택 사례에 실제 OpenAI 생성 호출을 실행합니다.",
    )
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        help="선택한 실제 호출이 API 비용을 사용할 수 있음을 확인합니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="결과 JSON 경로입니다. 생략하면 .ai_quality_runs에 저장합니다.",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "CANDIDATE"),
        type=Path,
        help="저장된 두 결과의 공통 사례를 비교하며 OpenAI를 호출하지 않습니다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """기본 조회와 명시적 유료 실행을 분리합니다."""

    args = _build_parser().parse_args(argv)
    cases = load_ai_quality_cases()

    if args.compare is not None:
        if args.live or args.confirm_paid or args.case_ids or args.output:
            print(
                "비교 모드는 실행·사례·출력 옵션과 함께 사용할 수 없습니다.",
                file=sys.stderr,
            )
            return 2
        try:
            baseline = load_benchmark_run(args.compare[0])
            candidate = load_benchmark_run(args.compare[1])
            comparisons = compare_benchmark_runs(baseline, candidate)
        except (OSError, ValueError) as error:
            print(f"결과 비교 실패: {error}", file=sys.stderr)
            return 3
        for comparison in comparisons:
            print(
                f"{comparison.case_id} | {comparison.outcome} | "
                f"오류 {comparison.baseline_failed_errors}→"
                f"{comparison.candidate_failed_errors} | "
                f"경고 {comparison.baseline_failed_warnings}→"
                f"{comparison.candidate_failed_warnings}"
            )
        return 1 if any(
            comparison.outcome == "regressed"
            for comparison in comparisons
        ) else 0

    if not args.live:
        selected_ids = set(args.case_ids)
        for case in cases:
            if not selected_ids or case.case_id in selected_ids:
                dimensions = ", ".join(case.quality_dimensions)
                print(
                    f"{case.case_id} | {case.feature} | "
                    f"수준 {case.learner_level} | {case.course_name} | "
                    f"{dimensions}"
                )
        if args.case_ids:
            print("\n조회 모드이므로 OpenAI API를 호출하지 않았습니다.")
        return 0

    try:
        validate_live_benchmark_request(
            live=args.live,
            confirm_paid=args.confirm_paid,
            case_ids=args.case_ids,
        )
        selected_cases = select_benchmark_cases(cases, args.case_ids)
    except ValueError as error:
        print(f"실행 조건 오류: {error}", file=sys.stderr)
        return 2

    print(
        f"선택한 {len(selected_cases)}개 사례에 실제 OpenAI 호출을 시작합니다."
    )
    run = run_live_benchmark(selected_cases)
    try:
        output_path = save_benchmark_run(run, args.output)
    except (FileExistsError, OSError) as error:
        print(f"결과 저장 실패: {error}", file=sys.stderr)
        return 3

    completed_count = sum(
        record.status == "completed" for record in run.records
    )
    acceptable_count = sum(
        record.report is not None and record.report.is_acceptable
        for record in run.records
    )
    print(f"결과 저장: {output_path}")
    print(
        f"생성 성공 {completed_count}/{len(run.records)} · "
        f"오류 기준 통과 {acceptable_count}/{len(run.records)}"
    )
    return 0 if completed_count == len(run.records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
