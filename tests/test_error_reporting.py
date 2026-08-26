import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from services.error_reporting import (
    MAX_LOG_DETAIL_CHARS,
    report_exception,
    sanitize_error_detail,
)
from views.error_feedback import (
    render_unexpected_error,
    render_unexpected_warning,
)


class ErrorReportingTests(unittest.TestCase):
    def test_sanitize_error_detail_redacts_tokens_and_passwords(self) -> None:
        error = RuntimeError(
            "Bearer secret.jwt.token "
            "access_token='access-secret' "
            "password='plain secret with spaces'"
        )

        detail = sanitize_error_detail(error)

        self.assertNotIn("secret.jwt.token", detail)
        self.assertNotIn("access-secret", detail)
        self.assertNotIn("plain secret with spaces", detail)
        self.assertEqual(detail.count("[REDACTED]"), 3)

    def test_sanitize_error_detail_limits_log_length(self) -> None:
        detail = sanitize_error_detail(RuntimeError("x" * 800))

        self.assertEqual(len(detail), MAX_LOG_DETAIL_CHARS + 1)
        self.assertTrue(detail.endswith("…"))

    def test_report_exception_returns_reference_and_safe_detail(self) -> None:
        with (
            patch(
                "services.error_reporting.secrets.token_hex",
                return_value="a1b2c3d4",
            ),
            patch("services.error_reporting.LOGGER.error") as log_error,
        ):
            error_id = report_exception(
                "quiz.submit",
                RuntimeError("authorization=top-secret"),
            )

        self.assertEqual(error_id, "A1B2C3D4")
        logged_arguments = log_error.call_args.args
        self.assertNotIn("top-secret", logged_arguments)
        self.assertEqual(
            logged_arguments[-1],
            "authorization=[REDACTED]",
        )

    def test_report_exception_rejects_dynamic_operation_names(self) -> None:
        with self.assertRaises(ValueError):
            report_exception(
                "quiz.submit/user@example.com",
                RuntimeError("fail"),
            )

    def test_render_unexpected_error_hides_internal_detail(self) -> None:
        with (
            patch(
                "views.error_feedback.report_exception",
                return_value="A1B2C3D4",
            ) as report,
            patch("views.error_feedback.st.error") as show_error,
        ):
            error = RuntimeError("access_token=must-not-appear")
            result = render_unexpected_error(
                error,
                operation="quiz.submit",
                user_message="퀴즈 제출에 실패했습니다.",
            )

        self.assertEqual(result, "A1B2C3D4")
        report.assert_called_once_with("quiz.submit", error)
        rendered_message = show_error.call_args.args[0]
        self.assertNotIn("must-not-appear", rendered_message)
        self.assertIn("퀴즈 제출에 실패했습니다.", rendered_message)
        self.assertIn("A1B2C3D4", rendered_message)

    def test_render_unexpected_warning_uses_warning_feedback(self) -> None:
        with (
            patch(
                "views.error_feedback.report_exception",
                return_value="11223344",
            ),
            patch("views.error_feedback.st.warning") as show_warning,
        ):
            render_unexpected_warning(
                RuntimeError("database detail"),
                operation="tutor.load_tasks",
                user_message="직접 질문만 사용할 수 있습니다.",
            )

        rendered_message = show_warning.call_args.args[0]
        self.assertNotIn("database detail", rendered_message)
        self.assertIn("11223344", rendered_message)

    def test_streamlit_error_messages_do_not_render_exceptions(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source_paths = [
            project_root / "app.py",
            *sorted((project_root / "views").glob("*.py")),
        ]
        violations: list[str] = []

        for source_path in source_paths:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    not isinstance(node, ast.Call)
                    or not isinstance(node.func, ast.Attribute)
                    or node.func.attr != "error"
                    or not node.args
                ):
                    continue
                exposed_names = {
                    child.id
                    for child in ast.walk(node.args[0])
                    if isinstance(child, ast.Name)
                    and child.id in {"error", "exception", "exc"}
                }
                if exposed_names:
                    violations.append(
                        f"{source_path.name}:{node.lineno}"
                    )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
