"""Supabase SQL manifest의 순서, 의존성, 파일 누락을 검사합니다."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "supabase" / "migrations.toml"
MIGRATION_ID_PATTERN = re.compile(r"^\d{3}_[a-z0-9_]+$")
TRANSACTION_BEGIN_PATTERN = re.compile(r"(?m)^\s*begin\s*;", re.IGNORECASE)
TRANSACTION_COMMIT_PATTERN = re.compile(r"(?m)^\s*commit\s*;", re.IGNORECASE)


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict:
    """TOML manifest를 읽어 일반 사전으로 반환합니다."""

    with path.open("rb") as manifest_file:
        return tomllib.load(manifest_file)


def _resolve_sql_root(manifest_path: Path, manifest: dict) -> Path:
    """manifest에 선언된 SQL 루트를 저장소 내부 절대 경로로 해석합니다."""

    sql_root_value = manifest.get("sql_root")
    if not isinstance(sql_root_value, str) or not sql_root_value.strip():
        raise ValueError("sql_root가 비어 있습니다.")
    sql_root = (manifest_path.parent / sql_root_value).resolve()
    if not sql_root.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError("sql_root는 저장소 내부 경로여야 합니다.")
    return sql_root


def _validate_sql_path(
    sql_root: Path,
    relative_path: object,
    label: str,
    errors: list[str],
) -> Path | None:
    """SQL 경로가 루트 밖으로 벗어나지 않고 실제 파일인지 검사합니다."""

    if not isinstance(relative_path, str) or not relative_path.strip():
        errors.append(f"{label}: SQL 경로가 비어 있습니다.")
        return None
    candidate = (sql_root / relative_path).resolve()
    if not candidate.is_relative_to(sql_root):
        errors.append(f"{label}: SQL 루트 밖의 경로입니다: {relative_path}")
        return None
    if candidate.suffix.casefold() != ".sql":
        errors.append(f"{label}: .sql 파일이 아닙니다: {relative_path}")
        return None
    if not candidate.is_file():
        errors.append(f"{label}: 파일을 찾을 수 없습니다: {relative_path}")
        return None
    return candidate


def validate_manifest(
    manifest: dict,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> list[str]:
    """manifest 구조와 전체 SQL 파일 분류를 검사해 오류 목록을 반환합니다."""

    errors: list[str] = []
    if manifest.get("manifest_version") != 1:
        errors.append("manifest_version은 1이어야 합니다.")

    try:
        sql_root = _resolve_sql_root(manifest_path, manifest)
    except ValueError as error:
        return [str(error)]

    migrations = manifest.get("migrations")
    if not isinstance(migrations, list) or not migrations:
        return [*errors, "migrations 목록이 비어 있습니다."]

    expected_orders = list(range(1, len(migrations) + 1))
    actual_orders = [item.get("order") for item in migrations]
    if actual_orders != expected_orders:
        errors.append("migration order는 1부터 빠짐없이 증가해야 합니다.")

    migration_ids: set[str] = set()
    accounted_paths: set[str] = set()
    previous_id: str | None = None
    for item in migrations:
        migration_id = item.get("id")
        label = f"migration {migration_id!r}"
        if not isinstance(migration_id, str) or not MIGRATION_ID_PATTERN.fullmatch(
            migration_id
        ):
            errors.append(f"{label}: ID 형식이 올바르지 않습니다.")
            continue
        if migration_id in migration_ids:
            errors.append(f"{label}: 중복 ID입니다.")
        migration_ids.add(migration_id)

        dependencies = item.get("depends_on")
        expected_dependencies = [] if previous_id is None else [previous_id]
        if dependencies != expected_dependencies:
            errors.append(
                f"{label}: depends_on은 {expected_dependencies!r}이어야 합니다."
            )
        previous_id = migration_id

        relative_path = item.get("path")
        migration_path = _validate_sql_path(
            sql_root,
            relative_path,
            label,
            errors,
        )
        if isinstance(relative_path, str):
            if relative_path in accounted_paths:
                errors.append(f"{label}: 중복 SQL 경로입니다: {relative_path}")
            accounted_paths.add(relative_path)
            if "validation" in Path(relative_path).stem.casefold():
                errors.append(f"{label}: 검증 SQL을 migration으로 등록했습니다.")
        if migration_path is not None:
            sql_text = migration_path.read_text(encoding="utf-8")
            if not TRANSACTION_BEGIN_PATTERN.search(sql_text):
                errors.append(f"{label}: begin 트랜잭션이 없습니다.")
            if not TRANSACTION_COMMIT_PATTERN.search(sql_text):
                errors.append(f"{label}: commit 트랜잭션이 없습니다.")

        validation_path = item.get("validation")
        if validation_path is not None:
            _validate_sql_path(
                sql_root,
                validation_path,
                f"{label} validation",
                errors,
            )
            if not isinstance(validation_path, str) or not validation_path.endswith(
                "_validation.sql"
            ):
                errors.append(f"{label}: validation 파일명이 올바르지 않습니다.")
            elif validation_path in accounted_paths:
                errors.append(f"{label}: 중복 SQL 경로입니다: {validation_path}")
            else:
                accounted_paths.add(validation_path)

    standalone_checks = manifest.get("standalone_checks", [])
    if not isinstance(standalone_checks, list):
        errors.append("standalone_checks는 목록이어야 합니다.")
        standalone_checks = []
    standalone_ids: set[str] = set()
    for item in standalone_checks:
        check_id = item.get("id")
        label = f"standalone check {check_id!r}"
        if not isinstance(check_id, str) or not check_id.strip():
            errors.append(f"{label}: ID가 비어 있습니다.")
        elif check_id in standalone_ids:
            errors.append(f"{label}: 중복 ID입니다.")
        else:
            standalone_ids.add(check_id)

        if item.get("after") not in migration_ids:
            errors.append(f"{label}: after migration을 찾을 수 없습니다.")
        elif item.get("after") != previous_id:
            errors.append(f"{label}: 마지막 migration 뒤에 실행되어야 합니다.")
        relative_path = item.get("path")
        _validate_sql_path(sql_root, relative_path, label, errors)
        if isinstance(relative_path, str):
            if relative_path in accounted_paths:
                errors.append(f"{label}: 중복 SQL 경로입니다: {relative_path}")
            accounted_paths.add(relative_path)

    discovered_paths = {
        path.name for path in sql_root.glob("supabase_*.sql") if path.is_file()
    }
    missing_from_manifest = sorted(discovered_paths - accounted_paths)
    missing_from_disk = sorted(accounted_paths - discovered_paths)
    if missing_from_manifest:
        errors.append(
            "manifest에 분류되지 않은 SQL: " + ", ".join(missing_from_manifest)
        )
    if missing_from_disk:
        errors.append(
            "저장소에 없는 manifest SQL: " + ", ".join(missing_from_disk)
        )
    return errors


def render_execution_plan(manifest: dict) -> str:
    """신규 프로젝트용 SQL 실행 순서를 사람이 읽기 쉽게 만듭니다."""

    lines = []
    for migration in manifest["migrations"]:
        line = f"{migration['order']:03d}  {migration['path']}"
        if migration.get("validation"):
            line += f"  ->  {migration['validation']}"
        lines.append(line)
    for check in manifest.get("standalone_checks", []):
        lines.append(
            f"CHECK after {check['after']}  {check['path']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """manifest 검사 CLI를 실행합니다."""

    parser = argparse.ArgumentParser(
        description="Supabase SQL migration manifest를 검사합니다."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="검사 성공 후 신규 프로젝트용 실행 순서를 표시합니다.",
    )
    args = parser.parse_args(argv)

    manifest = load_manifest()
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.list:
        print(render_execution_plan(manifest))
    print(
        "SQL migration manifest validation: success "
        f"({len(manifest['migrations'])} migrations, "
        f"{len(manifest.get('standalone_checks', []))} standalone checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
