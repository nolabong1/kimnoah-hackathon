import logging
import re
import secrets


LOGGER = logging.getLogger("kimnoah_hackathon")
MAX_LOG_DETAIL_CHARS = 500
_OPERATION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
_BEARER_PATTERN = re.compile(
    r"(?i)\bbearer\s+[a-z0-9._~+\-/]+=*"
)
_SENSITIVE_QUOTED_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(['\"]?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|password)['\"]?\s*[:=]\s*)"
    r"(['\"])[^'\"]*\2"
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(['\"]?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|password)['\"]?\s*[:=]\s*)"
    r"([^,\s}\]]+)"
)


def _normalize_operation(operation: str) -> str:
    """로그 집계를 위한 안전한 작업 식별자를 검증합니다."""

    normalized = operation.strip().casefold()
    if not _OPERATION_PATTERN.fullmatch(normalized):
        raise ValueError(
            "오류 작업 식별자는 영문 소문자, 숫자, 점, 밑줄, "
            "하이픈만 사용할 수 있습니다."
        )
    return normalized


def sanitize_error_detail(error: Exception) -> str:
    """예외 문자열의 대표 비밀값을 가리고 로그 길이를 제한합니다."""

    detail = " ".join(str(error).split())
    detail = _BEARER_PATTERN.sub("Bearer [REDACTED]", detail)
    detail = _SENSITIVE_QUOTED_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}[REDACTED]",
        detail,
    )
    detail = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}[REDACTED]",
        detail,
    )
    if len(detail) > MAX_LOG_DETAIL_CHARS:
        detail = f"{detail[:MAX_LOG_DETAIL_CHARS]}…"
    return detail or "(empty exception message)"


def report_exception(operation: str, error: Exception) -> str:
    """서버 로그에 안전한 진단 정보를 남기고 짧은 오류 ID를 반환합니다."""

    normalized_operation = _normalize_operation(operation)
    error_id = secrets.token_hex(4).upper()
    LOGGER.error(
        "operation_failed error_id=%s operation=%s error_type=%s detail=%s",
        error_id,
        normalized_operation,
        type(error).__name__,
        sanitize_error_detail(error),
    )
    return error_id
