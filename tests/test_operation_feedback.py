import unittest
from unittest.mock import MagicMock, patch

from views.operation_feedback import operation_status


class OperationFeedbackTests(unittest.TestCase):
    @patch("views.operation_feedback.st.status")
    def test_success_updates_the_same_status_container(self, mock_status):
        status = MagicMock()
        mock_status.return_value = status

        with operation_status("처리 중", "완료", "실패") as active_status:
            self.assertIs(active_status, status)

        mock_status.assert_called_once_with(
            "처리 중",
            state="running",
            expanded=True,
            width="stretch",
        )
        status.update.assert_called_once_with(
            label="완료",
            state="complete",
            expanded=False,
        )

    @patch("views.operation_feedback.st.status")
    def test_failure_marks_status_and_reraises(self, mock_status):
        status = MagicMock()
        mock_status.return_value = status

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with operation_status("처리 중", "완료", "실패"):
                raise RuntimeError("boom")

        status.update.assert_called_once_with(
            label="실패",
            state="error",
            expanded=True,
        )


if __name__ == "__main__":
    unittest.main()
