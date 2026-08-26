import os
import threading
import unittest
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions


RUN_ENV_KEY = "RUN_SUPABASE_INTEGRATION_TESTS"
DESTRUCTIVE_CONFIRMATION = "dedicated-test-project-only"


@dataclass(frozen=True)
class SupabaseIntegrationConfig:
    """전용 Supabase 통합 테스트 프로젝트 연결 설정입니다."""

    url: str
    publishable_key: str
    service_role_key: str
    project_ref: str

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> "SupabaseIntegrationConfig":
        required_keys = (
            "SUPABASE_TEST_URL",
            "SUPABASE_TEST_PUBLISHABLE_KEY",
            "SUPABASE_TEST_SERVICE_ROLE_KEY",
            "SUPABASE_TEST_PROJECT_REF",
            "SUPABASE_TEST_CONFIRM_PROJECT_REF",
            "SUPABASE_TEST_ALLOW_DESTRUCTIVE",
        )
        missing = [key for key in required_keys if not environment.get(key)]
        if missing:
            raise RuntimeError(
                "Supabase 통합 테스트 환경변수가 부족합니다: "
                + ", ".join(missing)
            )

        url = environment["SUPABASE_TEST_URL"].rstrip("/")
        publishable_key = environment["SUPABASE_TEST_PUBLISHABLE_KEY"]
        service_role_key = environment["SUPABASE_TEST_SERVICE_ROLE_KEY"]
        project_ref = environment["SUPABASE_TEST_PROJECT_REF"].strip()
        confirmed_ref = environment[
            "SUPABASE_TEST_CONFIRM_PROJECT_REF"
        ].strip()
        destructive_confirmation = environment[
            "SUPABASE_TEST_ALLOW_DESTRUCTIVE"
        ]

        if destructive_confirmation != DESTRUCTIVE_CONFIRMATION:
            raise RuntimeError(
                "전용 테스트 프로젝트 삭제 동작을 명시적으로 확인해야 합니다."
            )
        if project_ref != confirmed_ref:
            raise RuntimeError("테스트 프로젝트 참조 확인값이 일치하지 않습니다.")
        if publishable_key == service_role_key:
            raise RuntimeError(
                "publishable 키와 service role 키가 같을 수 없습니다."
            )

        parsed_url = urlparse(url)
        hostname = (parsed_url.hostname or "").casefold()
        is_local = hostname in {"127.0.0.1", "localhost"}
        if not is_local and hostname != f"{project_ref}.supabase.co":
            raise RuntimeError(
                "SUPABASE_TEST_URL과 테스트 프로젝트 참조가 일치하지 않습니다."
            )

        application_url = environment.get("SUPABASE_URL", "").rstrip("/")
        if application_url and application_url == url:
            raise RuntimeError("운영 애플리케이션 Supabase URL에서는 실행할 수 없습니다.")

        return cls(
            url=url,
            publishable_key=publishable_key,
            service_role_key=service_role_key,
            project_ref=project_ref,
        )


@dataclass(frozen=True)
class IntegrationUser:
    """통합 테스트가 생성하고 종료 시 삭제하는 임시 사용자입니다."""

    id: str
    email: str
    password: str
    client: Client


def _client_options() -> SyncClientOptions:
    return SyncClientOptions(
        postgrest_client_timeout=20,
        function_client_timeout=20,
    )


def _create_authenticated_client(
    config: SupabaseIntegrationConfig,
    email: str,
    password: str,
) -> Client:
    client = create_client(
        config.url,
        config.publishable_key,
        options=_client_options(),
    )
    auth_response = client.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    if auth_response.user is None or auth_response.session is None:
        raise RuntimeError("통합 테스트 사용자 로그인에 실패했습니다.")
    return client


def _build_plan_payload(title: str) -> dict:
    start_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    schedule = {f"{day_offset}일차": 60 for day_offset in range(7)}
    overview = [
        {
            "day_offset": day_offset,
            "daily_focus": f"{day_offset + 1}일차 통합 테스트",
            "total_minutes": 10,
        }
        for day_offset in range(7)
    ]
    tasks = [
        {
            "day_offset": day_offset,
            "title": f"{day_offset + 1}일차 통합 테스트 과제",
            "description": "실제 Supabase 보안 경계를 확인하는 임시 과제입니다.",
            "task_type": "learn",
            "estimated_minutes": 10,
        }
        for day_offset in range(7)
    ]
    return {
        "p_title": title,
        "p_course_name": "통합 테스트",
        "p_goal": "RLS와 원자적 RPC 동작 검증",
        "p_current_level": 3,
        "p_start_date": start_date.isoformat(),
        "p_available_schedule": schedule,
        "p_weekly_overview": overview,
        "p_tasks": tasks,
    }


def _save_test_plan(client: Client, title: str) -> dict:
    response = client.rpc(
        "save_weekly_study_plan_with_tasks",
        _build_plan_payload(title),
    ).execute()
    if not isinstance(response.data, dict):
        raise RuntimeError("통합 테스트 계획 저장 결과가 비어 있습니다.")
    return response.data


def _assert_permission_denied(
    test_case: unittest.TestCase,
    operation,
) -> None:
    with test_case.assertRaises(APIError) as raised:
        operation()
    test_case.assertEqual(raised.exception.code, "42501")


class SupabaseIntegrationConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "SUPABASE_TEST_URL": "https://testref.supabase.co",
            "SUPABASE_TEST_PUBLISHABLE_KEY": "publishable-test-key",
            "SUPABASE_TEST_SERVICE_ROLE_KEY": "service-test-key",
            "SUPABASE_TEST_PROJECT_REF": "testref",
            "SUPABASE_TEST_CONFIRM_PROJECT_REF": "testref",
            "SUPABASE_TEST_ALLOW_DESTRUCTIVE": DESTRUCTIVE_CONFIRMATION,
        }

    def test_safe_dedicated_project_configuration_is_accepted(self):
        config = SupabaseIntegrationConfig.from_environment(
            MappingProxyType(self.environment)
        )

        self.assertEqual(config.project_ref, "testref")
        self.assertEqual(config.url, "https://testref.supabase.co")

    def test_operating_project_url_is_rejected(self):
        environment = dict(self.environment)
        environment["SUPABASE_URL"] = environment["SUPABASE_TEST_URL"]

        with self.assertRaises(RuntimeError):
            SupabaseIntegrationConfig.from_environment(environment)

    def test_project_reference_must_be_confirmed_twice(self):
        environment = dict(self.environment)
        environment["SUPABASE_TEST_CONFIRM_PROJECT_REF"] = "otherref"

        with self.assertRaises(RuntimeError):
            SupabaseIntegrationConfig.from_environment(environment)

    def test_destructive_confirmation_is_required(self):
        environment = dict(self.environment)
        environment["SUPABASE_TEST_ALLOW_DESTRUCTIVE"] = "yes"

        with self.assertRaises(RuntimeError):
            SupabaseIntegrationConfig.from_environment(environment)


@unittest.skipUnless(
    os.getenv(RUN_ENV_KEY) == "1",
    "전용 Supabase 프로젝트 통합 테스트가 비활성화되어 있습니다.",
)
class SupabaseSecurityIntegrationTests(unittest.TestCase):
    """전용 프로젝트에서만 실행하는 실제 RLS·권한·동시성 검사입니다."""

    config: SupabaseIntegrationConfig
    admin_client: Client
    user_a: IntegrationUser
    user_b: IntegrationUser
    created_user_ids: list[str] = []

    @classmethod
    def setUpClass(cls):
        cls.config = SupabaseIntegrationConfig.from_environment(os.environ)
        cls.admin_client = create_client(
            cls.config.url,
            cls.config.service_role_key,
            options=_client_options(),
        )
        cls.created_user_ids = []

        try:
            cls.user_a = cls._create_user("a")
            cls.user_b = cls._create_user("b")
        except Exception:
            cls._delete_created_users()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._delete_created_users()

    @classmethod
    def _create_user(cls, label: str) -> IntegrationUser:
        unique_value = uuid4().hex
        email = f"codex-integration-{label}-{unique_value}@example.com"
        password = f"Aa!9-{unique_value}"
        response = cls.admin_client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "nickname": f"통합 테스트 {label.upper()}",
                },
            }
        )
        if response.user is None:
            raise RuntimeError("통합 테스트 임시 사용자 생성에 실패했습니다.")
        user_id = str(response.user.id)
        cls.created_user_ids.append(user_id)
        return IntegrationUser(
            id=user_id,
            email=email,
            password=password,
            client=_create_authenticated_client(
                cls.config,
                email,
                password,
            ),
        )

    @classmethod
    def _delete_created_users(cls):
        for user_id in reversed(cls.created_user_ids):
            try:
                cls.admin_client.auth.admin.delete_user(user_id)
            except Exception:
                pass
        cls.created_user_ids = []

    def test_user_cannot_read_or_delete_other_users_plan(self):
        plan = _save_test_plan(
            self.user_a.client,
            f"RLS 소유권 {uuid4().hex[:8]}",
        )
        task = (
            self.user_a.client.table("study_tasks")
            .select("id,status")
            .eq("plan_id", plan["id"])
            .limit(1)
            .execute()
            .data[0]
        )

        read_response = (
            self.user_b.client.table("study_plans")
            .select("id")
            .eq("id", plan["id"])
            .execute()
        )
        delete_response = (
            self.user_b.client.table("study_plans")
            .delete()
            .eq("id", plan["id"])
            .execute()
        )

        self.assertFalse(read_response.data)
        self.assertFalse(delete_response.data)
        owner_response = (
            self.user_a.client.table("study_plans")
            .select("id")
            .eq("id", plan["id"])
            .execute()
        )
        self.assertEqual(len(owner_response.data or []), 1)

        with self.assertRaises(APIError):
            self.user_b.client.rpc(
                "complete_study_task_with_gamification",
                {"p_task_id": task["id"]},
            ).execute()
        task_after_denied_request = (
            self.user_a.client.table("study_tasks")
            .select("status")
            .eq("id", task["id"])
            .single()
            .execute()
            .data
        )
        self.assertEqual(task_after_denied_request["status"], "pending")

    def test_authenticated_client_cannot_write_core_tables_directly(self):
        plan = _save_test_plan(
            self.user_a.client,
            f"직접 쓰기 차단 {uuid4().hex[:8]}",
        )
        task = (
            self.user_a.client.table("study_tasks")
            .select("id")
            .eq("plan_id", plan["id"])
            .limit(1)
            .execute()
            .data[0]
        )
        start_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
        anonymous_client = create_client(
            self.config.url,
            self.config.publishable_key,
            options=_client_options(),
        )

        _assert_permission_denied(
            self,
            lambda: anonymous_client.rpc(
                "save_weekly_study_plan_with_tasks",
                _build_plan_payload("익명 RPC 실행 차단"),
            ).execute(),
        )

        _assert_permission_denied(
            self,
            lambda: self.user_a.client.table("study_plans").insert(
                {
                    "user_id": self.user_a.id,
                    "title": "직접 생성 차단",
                    "course_name": "보안 테스트",
                    "goal": "직접 INSERT 거부",
                    "current_level": 3,
                    "start_date": start_date.isoformat(),
                    "target_date": (start_date + timedelta(days=6)).isoformat(),
                    "available_schedule": {},
                    "weekly_overview": [],
                    "status": "active",
                }
            ).execute(),
        )
        _assert_permission_denied(
            self,
            lambda: self.user_a.client.table("study_tasks")
            .update({"status": "skipped"})
            .eq("id", task["id"])
            .execute(),
        )
        _assert_permission_denied(
            self,
            lambda: self.user_a.client.table("quizzes").insert(
                {
                    "user_id": self.user_a.id,
                    "plan_id": plan["id"],
                    "task_id": task["id"],
                    "title": "직접 퀴즈 생성 차단",
                    "questions": [],
                    "question_count": 1,
                }
            ).execute(),
        )

    def test_plan_rpc_saves_complete_structure_and_rejects_invalid_snapshot(self):
        title = f"원자 저장 {uuid4().hex[:8]}"
        plan = _save_test_plan(self.user_a.client, title)
        tasks = (
            self.user_a.client.table("study_tasks")
            .select("id,user_id,plan_id,scheduled_date,status,source_type")
            .eq("plan_id", plan["id"])
            .order("scheduled_date")
            .execute()
            .data
        )

        self.assertEqual(plan["user_id"], self.user_a.id)
        self.assertEqual(len(tasks), 7)
        self.assertTrue(
            all(
                task["user_id"] == self.user_a.id
                and task["plan_id"] == plan["id"]
                and task["status"] == "pending"
                and task["source_type"] == "weekly_plan"
                for task in tasks
            )
        )

        before_response = (
            self.user_a.client.table("study_plans")
            .select("id")
            .execute()
        )
        invalid_payload = _build_plan_payload(
            f"잘못된 스냅샷 {uuid4().hex[:8]}"
        )
        invalid_payload["p_weekly_overview"][0]["total_minutes"] = 11
        with self.assertRaises(APIError):
            self.user_a.client.rpc(
                "save_weekly_study_plan_with_tasks",
                invalid_payload,
            ).execute()
        after_response = (
            self.user_a.client.table("study_plans")
            .select("id")
            .execute()
        )
        self.assertEqual(
            len(before_response.data or []),
            len(after_response.data or []),
        )

    def test_concurrent_task_completion_awards_task_exp_once(self):
        plan = _save_test_plan(
            self.user_a.client,
            f"동시 완료 {uuid4().hex[:8]}",
        )
        today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        task = (
            self.user_a.client.table("study_tasks")
            .select("id")
            .eq("plan_id", plan["id"])
            .eq("scheduled_date", today)
            .limit(1)
            .execute()
            .data[0]
        )
        second_client = _create_authenticated_client(
            self.config,
            self.user_a.email,
            self.user_a.password,
        )
        barrier = threading.Barrier(2)

        def complete(client: Client) -> dict:
            barrier.wait(timeout=5)
            response = client.rpc(
                "complete_study_task_with_gamification",
                {"p_task_id": task["id"]},
            ).execute()
            if not isinstance(response.data, dict):
                raise RuntimeError("동시 완료 RPC 결과가 비어 있습니다.")
            return response.data

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(complete, client)
                for client in (self.user_a.client, second_client)
            ]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual(sum(result["task_exp"] for result in results), 10)
        self.assertEqual(
            sum(bool(result["already_completed"]) for result in results),
            1,
        )
        exp_events = (
            self.user_a.client.table("exp_events")
            .select("id,amount")
            .eq("source_key", f"task:{task['id']}")
            .execute()
            .data
        )
        self.assertEqual(len(exp_events), 1)
        self.assertEqual(exp_events[0]["amount"], 10)


if __name__ == "__main__":
    unittest.main()
