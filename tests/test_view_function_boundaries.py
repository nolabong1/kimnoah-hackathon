import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from views.auth_session_storage import (
    AUTH_STORAGE_SYNCED_TOKEN_KEY,
    _apply_auth_storage_ack,
    _sync_authenticated_session,
)
from views.quiz_ui import (
    _get_or_create_submission_request,
    _group_mastery_changes,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as error:
            raise AttributeError(key) from error

    def __setattr__(self, key, value):
        self[key] = value


def get_function_length(path: str, function_name: str) -> int:
    source = (PROJECT_ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return function.end_lineno - function.lineno + 1


class ViewFunctionBoundaryTests(unittest.TestCase):
    def test_public_view_orchestrators_stay_small(self):
        self.assertLessEqual(
            get_function_length("views/quiz_ui.py", "render_quiz_section"),
            90,
        )
        self.assertLessEqual(
            get_function_length(
                "views/mastery_dashboard_view.py",
                "render_mastery_dashboard",
            ),
            60,
        )
        self.assertLessEqual(
            get_function_length(
                "views/auth_session_storage.py",
                "initialize_auth_session",
            ),
            40,
        )


class QuizStateHelperTests(unittest.TestCase):
    def test_same_submission_reuses_idempotency_key(self):
        existing = {
            "submission_key": "stable-key",
            "quiz_updated_at": "2026-08-26T00:00:00+00:00",
            "answers": [0, 1, 2, 3, 0],
        }

        result = _get_or_create_submission_request(
            existing_request=existing,
            quiz_updated_at="2026-08-26T00:00:00+00:00",
            answers=[0, 1, 2, 3, 0],
        )

        self.assertIs(result, existing)

    def test_changed_answers_create_new_idempotency_key(self):
        existing = {
            "submission_key": "old-key",
            "quiz_updated_at": "2026-08-26T00:00:00+00:00",
            "answers": [0, 1, 2, 3, 0],
        }

        result = _get_or_create_submission_request(
            existing_request=existing,
            quiz_updated_at="2026-08-26T00:00:00+00:00",
            answers=[1, 1, 2, 3, 0],
        )

        self.assertNotEqual(result["submission_key"], "old-key")
        self.assertEqual(result["answers"], [1, 1, 2, 3, 0])

    def test_mastery_changes_are_grouped_and_invalid_rows_are_ignored(self):
        changes = _group_mastery_changes(
            [
                {"concept_id": "concept-a", "question_index": 0},
                {"concept_id": "concept-a", "question_index": 2},
                {"concept_id": "concept-b", "question_index": 1},
                {"concept_id": None, "question_index": 3},
                "invalid",
            ]
        )

        self.assertEqual(
            [item["question_index"] for item in changes["concept-a"]],
            [0, 2],
        )
        self.assertEqual(len(changes["concept-b"]), 1)
        self.assertNotIn(None, changes)


class AuthStateHelperTests(unittest.TestCase):
    def test_write_ack_records_only_written_refresh_token(self):
        state = SessionState()
        streamlit_stub = SimpleNamespace(session_state=state)
        command = {
            "action": "write",
            "session": {
                "access_token": "access",
                "refresh_token": "refresh",
            },
        }

        with patch("views.auth_session_storage.st", streamlit_stub):
            _apply_auth_storage_ack(command, {"ok": True})

        self.assertEqual(
            state[AUTH_STORAGE_SYNCED_TOKEN_KEY],
            "refresh",
        )

    def test_pending_same_token_does_not_queue_duplicate_write(self):
        state = SessionState(
            auth_user=SimpleNamespace(id="user-id"),
            auth_storage_command={
                "action": "write",
                "session": {"refresh_token": "same-refresh"},
            },
        )
        streamlit_stub = SimpleNamespace(session_state=state)
        supabase = SimpleNamespace(
            auth=SimpleNamespace(get_session=lambda: object())
        )

        with (
            patch("views.auth_session_storage.st", streamlit_stub),
            patch(
                "views.auth_session_storage.get_session_tokens",
                return_value={
                    "access_token": "access",
                    "refresh_token": "same-refresh",
                },
            ),
            patch(
                "views.auth_session_storage.queue_auth_storage_command"
            ) as queue_command,
        ):
            _sync_authenticated_session(supabase)

        queue_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
