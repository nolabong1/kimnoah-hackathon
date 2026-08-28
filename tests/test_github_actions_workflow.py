import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


class GitHubActionsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci_runs_required_offline_checks(self):
        self.assertIn("python -m compileall -q", self.workflow)
        self.assertIn(
            "python tools/validate_sql_migrations.py",
            self.workflow,
        )
        self.assertIn(
            'python -m unittest discover -s tests -p "test_*.py"',
            self.workflow,
        )
        self.assertIn('RUN_SUPABASE_INTEGRATION_TESTS: "0"', self.workflow)

    def test_ci_uses_read_only_permissions_without_secrets(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("OPENAI_API_KEY", self.workflow)
        self.assertNotIn("SUPABASE_TEST_SERVICE_ROLE_KEY", self.workflow)

    def test_official_actions_are_pinned_to_full_commit_shas(self):
        action_references = re.findall(
            r"uses:\s+(actions/[^@\s]+)@([^\s]+)",
            self.workflow,
        )

        self.assertEqual(
            {action for action, _reference in action_references},
            {"actions/checkout", "actions/setup-python"},
        )
        self.assertTrue(
            all(
                re.fullmatch(r"[0-9a-f]{40}", reference)
                for _action, reference in action_references
            )
        )


if __name__ == "__main__":
    unittest.main()
