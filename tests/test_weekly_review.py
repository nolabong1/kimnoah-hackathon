import json
import unittest
from datetime import date
from unittest.mock import patch

from models.study_plan import (
    DailyStudyPlan,
    StudyTaskDraft,
    WeeklyStudyPlan,
)
from models.learning_blueprint import LearningEvidenceRequirement
from models.learning_objective import LearningObjectiveContract
from models.weekly_review import WeeklyReviewAnalysis
from services.study_plan_service import generate_weekly_study_plan
from services.study_plan_repository import (
    complete_study_plan_for_weekly_review_test,
)
from services.weekly_review_repository import update_weekly_review
from services.weekly_review_service import (
    REFLECTION_QUESTIONS,
    WeeklyReviewValidationError,
    build_weekly_review_context,
    calculate_weekly_statistics,
    convert_weekly_review_to_markdown,
    generate_weekly_review,
    get_default_next_plan_start_date,
    is_plan_fully_completed,
    is_weekly_review_eligible,
    validate_reflection_answers,
)
from views.weekly_review_state import (
    COMPLETED_PLAN_PENDING_KEY,
    NEXT_PLAN_DRAFT_KEY,
    NEXT_PLAN_SAVED_ID_KEY,
    NEXT_PLAN_SAVED_KEY,
    PLAN_SELECT_KEY,
    PENDING_NAVIGATION_KEY,
    apply_selected_plan_state,
    clear_weekly_review_state,
    create_next_plan_draft_state,
    request_weekly_review_navigation,
)


USER_ID = "00000000-0000-0000-0000-000000000001"
PLAN_ID = "00000000-0000-0000-0000-000000000002"
REVIEW_ID = "00000000-0000-0000-0000-000000000003"


def build_plan(target_date: str = "2026-08-07") -> dict:
    return {
        "id": PLAN_ID,
        "title": "파이썬 7일 계획",
        "course_name": "Python",
        "goal": "반복문 익히기",
        "current_level": 3,
        "start_date": "2026-08-01",
        "target_date": target_date,
        "available_schedule": {f"{day}일차": 60 for day in range(7)},
    }


def build_task(
    *,
    status: str,
    task_type: str = "learn",
    scheduled_date: str = "2026-08-01",
    estimated_minutes: int = 30,
) -> dict:
    return {
        "status": status,
        "task_type": task_type,
        "scheduled_date": scheduled_date,
        "estimated_minutes": estimated_minutes,
    }


def build_analysis() -> WeeklyReviewAnalysis:
    return WeeklyReviewAnalysis(
        weekly_summary="총 3개 과제 중 2개를 완료했습니다.",
        achievements=["학습 과제 한 개와 퀴즈 한 개를 완료했습니다."],
        difficulties=["복습 과제 한 개가 대기 상태입니다."],
        learning_pattern_analysis="두 예정일에 완료 과제가 분포했습니다.",
        effective_strategies=["짧은 학습 뒤 퀴즈로 확인하는 방식을 유지합니다."],
        improvement_points=["대기 중인 복습을 다음 주 초에 배치합니다."],
        recommended_next_goal="반복문 문제 5개를 풀고 오답을 한 번 복습합니다.",
        recommended_strategy="학습, 연습, 복습 순서로 진행합니다.",
        recommended_workload_adjustment="maintain",
        workload_reason="완료율과 대기 과제를 함께 보면 유지가 현실적입니다.",
        motivation_message="완료한 흐름을 유지하며 대기 과제를 정리해보세요.",
    )


def build_weekly_plan() -> WeeklyStudyPlan:
    objectives = [
        LearningObjectiveContract(
            objective_key="loop_fundamentals",
            title="반복문 기본 원리",
            description="반복문의 실행 순서와 종료 조건을 설명합니다.",
            target_depth="foundation",
            evidence_requirements=[
                LearningEvidenceRequirement(
                    key="explain",
                    description="반복 실행 순서를 설명할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="apply",
                    description="반복문 예제를 작성할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="differentiate",
                    description="반복 조건의 차이를 구분할 수 있습니다.",
                ),
            ],
        ),
        LearningObjectiveContract(
            objective_key="loop_problem_solving",
            title="반복문 문제 해결",
            description="문제 조건을 반복 구조로 변환해 해결합니다.",
            target_depth="foundation",
            evidence_requirements=[
                LearningEvidenceRequirement(
                    key="explain",
                    description="반복 구조 선택 이유를 설명할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="apply",
                    description="문제를 반복 코드로 해결할 수 있습니다.",
                ),
                LearningEvidenceRequirement(
                    key="differentiate",
                    description="잘못된 종료 조건을 구분할 수 있습니다.",
                ),
            ],
        ),
    ]
    return WeeklyStudyPlan(
        title="다음 파이썬 계획",
        course_name="Python",
        level_assessment="기초 개념을 활용하는 단계입니다.",
        weekly_goal="반복문 문제를 해결합니다.",
        strategy="매일 짧게 연습합니다.",
        learning_objectives=objectives,
        days=[
            DailyStudyPlan(
                day_offset=day_offset,
                daily_focus=f"{day_offset + 1}일차 목표",
                tasks=[
                    StudyTaskDraft(
                        objective_key=(
                            "loop_fundamentals"
                            if day_offset < 4
                            else "loop_problem_solving"
                        ),
                        title="반복문 연습",
                        description="예제 한 개를 작성합니다.",
                        task_type="learn",
                        estimated_minutes=30,
                    )
                ],
            )
            for day_offset in range(7)
        ],
        motivation_message="일관되게 진행해보세요.",
    )


class FakeParsedResponse:
    def __init__(self, output_parsed):
        self.output_parsed = output_parsed


class FakeResponses:
    def __init__(self, output_parsed):
        self.output_parsed = output_parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return FakeParsedResponse(self.output_parsed)


class FakeOpenAIClient:
    def __init__(self, output_parsed):
        self.responses = FakeResponses(output_parsed)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeUpdateRequest:
    def __init__(self):
        self.operation = None
        self.payload = None
        self.filters = {}

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def execute(self):
        return FakeResponse([{"id": REVIEW_ID, **self.payload}])


class FakeSupabase:
    def __init__(self):
        self.request = FakeUpdateRequest()

    def table(self, table_name):
        if table_name != "weekly_learning_reviews":
            raise AssertionError("unexpected table")
        return self.request


class FakeRpcRequest:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return FakeResponse(self.data)


class FakeRpcSupabase:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeRpcRequest(self.data)


class WeeklyReviewEligibilityTests(unittest.TestCase):
    def test_all_completed_future_plan_is_eligible(self):
        plan = build_plan("2026-08-20")
        tasks = [build_task(status="completed")]
        self.assertTrue(
            is_weekly_review_eligible(plan, tasks, date(2026, 8, 10))
        )

    def test_target_date_passed_plan_is_eligible_with_pending_task(self):
        tasks = [build_task(status="pending")]
        self.assertTrue(
            is_weekly_review_eligible(build_plan(), tasks, date(2026, 8, 8))
        )

    def test_active_incomplete_plan_is_not_eligible(self):
        plan = build_plan("2026-08-20")
        tasks = [build_task(status="completed"), build_task(status="pending")]
        self.assertFalse(
            is_weekly_review_eligible(plan, tasks, date(2026, 8, 10))
        )

    def test_plan_completion_includes_the_successful_pending_task(self):
        tasks = [
            {"id": "task-1", "status": "completed"},
            {"id": "task-2", "status": "pending"},
        ]

        self.assertFalse(is_plan_fully_completed(tasks))
        self.assertTrue(
            is_plan_fully_completed(
                tasks,
                completing_task_id="task-2",
            )
        )

    def test_empty_or_partially_completed_plan_is_not_fully_completed(self):
        self.assertFalse(is_plan_fully_completed([]))
        self.assertFalse(
            is_plan_fully_completed(
                [
                    {"id": "task-1", "status": "completed"},
                    {"id": "task-2", "status": "skipped"},
                ]
            )
        )


class WeeklyStatisticsTests(unittest.TestCase):
    def test_zero_task_statistics_are_safe_and_serializable(self):
        statistics = calculate_weekly_statistics(build_plan(), [])
        self.assertEqual(statistics.total_tasks, 0)
        self.assertEqual(statistics.completion_rate, 0.0)
        self.assertEqual(statistics.completed_estimated_minutes, 0)
        self.assertEqual(
            statistics.model_dump(mode="json")["plan_start_date"],
            "2026-08-01",
        )

    def test_counts_minutes_types_and_daily_aggregation(self):
        tasks = [
            build_task(status="completed", task_type="learn", estimated_minutes=30),
            build_task(
                status="completed",
                task_type="quiz",
                scheduled_date="2026-08-02",
                estimated_minutes=20,
            ),
            build_task(
                status="pending",
                task_type="review",
                scheduled_date="2026-08-02",
                estimated_minutes=25,
            ),
            build_task(
                status="skipped",
                task_type="review",
                scheduled_date="2026-08-03",
                estimated_minutes=15,
            ),
        ]
        statistics = calculate_weekly_statistics(build_plan(), tasks)

        self.assertEqual(statistics.total_tasks, 4)
        self.assertEqual(statistics.completed_tasks, 2)
        self.assertEqual(statistics.pending_tasks, 1)
        self.assertEqual(statistics.skipped_tasks, 1)
        self.assertEqual(statistics.completion_rate, 50.0)
        self.assertEqual(statistics.total_planned_minutes, 90)
        self.assertEqual(statistics.completed_estimated_minutes, 50)
        self.assertEqual(statistics.scheduled_study_days, 3)
        self.assertEqual(statistics.days_with_completed_task, 2)
        self.assertEqual(
            statistics.completed_by_task_type,
            {"learn": 1, "review": 0, "quiz": 1},
        )
        self.assertEqual(
            statistics.completed_estimated_minutes_by_date,
            {"2026-08-01": 30, "2026-08-02": 20, "2026-08-03": 0},
        )
        self.assertEqual(
            statistics.task_completion_counts_by_date,
            {"2026-08-01": 1, "2026-08-02": 1, "2026-08-03": 0},
        )


class WeeklyReviewServiceTests(unittest.TestCase):
    def test_requires_at_least_one_reflection_answer(self):
        with self.assertRaises(WeeklyReviewValidationError):
            validate_reflection_answers(
                {key: "   " for key in REFLECTION_QUESTIONS}
            )
        cleaned = validate_reflection_answers({"went_well": "  꾸준함  "})
        self.assertEqual(cleaned["went_well"], "꾸준함")

    def test_markdown_rendering_is_deterministic(self):
        markdown = convert_weekly_review_to_markdown(build_analysis())
        expected_headings = [
            "## 이번 주 요약",
            "## 잘된 점",
            "## 어려웠던 점",
            "## 학습 패턴",
            "## 유지할 학습전략",
            "## 개선할 점",
            "## 다음 주 추천 목표",
            "## 다음 주 학습전략",
            "## 학습량 조정",
            "## 응원 메시지",
        ]
        positions = [markdown.index(heading) for heading in expected_headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("**유지하기**", markdown)

    def test_next_plan_start_date_uses_later_date(self):
        self.assertEqual(
            get_default_next_plan_start_date("2026-08-20", date(2026, 8, 10)),
            date(2026, 8, 21),
        )
        self.assertEqual(
            get_default_next_plan_start_date("2026-08-07", date(2026, 8, 10)),
            date(2026, 8, 10),
        )

    def test_next_plan_context_contains_only_approved_fields(self):
        statistics = calculate_weekly_statistics(
            build_plan(),
            [build_task(status="completed")],
        )

    @patch("services.weekly_review_service.get_openai_model", return_value="test")
    @patch("services.weekly_review_service.get_openai_client")
    def test_weekly_review_generation_calls_openai_once(
        self,
        mock_client,
        _mock_model,
    ):
        fake_client = FakeOpenAIClient(build_analysis())
        mock_client.return_value = fake_client
        statistics = calculate_weekly_statistics(
            build_plan(),
            [build_task(status="completed")],
        )

        analysis = generate_weekly_review(
            statistics,
            {"went_well": "정해진 과제를 완료했습니다."},
        )

        self.assertEqual(analysis.recommended_workload_adjustment, "maintain")
        self.assertEqual(len(fake_client.responses.calls), 1)

    @patch("services.weekly_review_service.get_openai_client")
    def test_empty_reflection_does_not_create_openai_client(self, mock_client):
        statistics = calculate_weekly_statistics(build_plan(), [])
        with self.assertRaises(WeeklyReviewValidationError):
            generate_weekly_review(statistics, {})
        mock_client.assert_not_called()
        context = build_weekly_review_context(
            statistics,
            build_analysis(),
            {"improvement_intention": "복습을 앞당기기"},
        )
        self.assertEqual(
            set(context),
            {
                "previous_completion_rate",
                "completed_estimated_minutes",
                "task_type_completion_counts",
                "ai_recommended_goal",
                "ai_recommended_strategy",
                "workload_adjustment",
                "user_improvement_intention",
            },
        )

    @patch("services.study_plan_service.get_openai_model", return_value="test")
    @patch("services.study_plan_service.get_openai_client")
    def test_existing_plan_generation_works_without_review_context(
        self,
        mock_client,
        _mock_model,
    ):
        fake_client = FakeOpenAIClient(build_weekly_plan())
        mock_client.return_value = fake_client
        schedule = {f"{day}일차": 60 for day in range(7)}

        result = generate_weekly_study_plan(
            course_name="Python",
            goal="반복문 익히기",
            current_level=3,
            available_schedule=schedule,
        )

        self.assertEqual(result.course_name, "Python")
        request_body = json.loads(
            fake_client.responses.calls[0]["input"][1]["content"]
        )
        self.assertNotIn("previous_week_review_context", request_body)
        self.assertNotIn("recent_assessment_score", request_body)

    @patch("services.study_plan_service.get_openai_model", return_value="test")
    @patch("services.study_plan_service.get_openai_client")
    def test_next_plan_generation_includes_review_context(
        self,
        mock_client,
        _mock_model,
    ):
        fake_client = FakeOpenAIClient(build_weekly_plan())
        mock_client.return_value = fake_client
        schedule = {f"{day}일차": 60 for day in range(7)}
        review_context = {"previous_completion_rate": 80.0}

        generate_weekly_study_plan(
            course_name="Python",
            goal="반복문 익히기",
            current_level=3,
            available_schedule=schedule,
            weekly_review_context=review_context,
            recent_score=75,
        )

        request_body = json.loads(
            fake_client.responses.calls[0]["input"][1]["content"]
        )
        self.assertEqual(
            request_body["previous_week_review_context"],
            review_context,
        )
        self.assertEqual(request_body["recent_assessment_score"], 75)

    @patch("services.study_plan_service.get_openai_model", return_value="test")
    @patch("services.study_plan_service.get_openai_client")
    def test_plan_generation_rejects_depth_that_conflicts_with_level(
        self,
        mock_client,
        _mock_model,
    ):
        invalid_plan = build_weekly_plan()
        invalid_plan.learning_objectives[0].target_depth = "developing"
        fake_client = FakeOpenAIClient(invalid_plan)
        mock_client.return_value = fake_client

        with self.assertRaisesRegex(RuntimeError, "계획을 생성하지 못했습니다"):
            generate_weekly_study_plan(
                course_name="Python",
                goal="반복문 익히기",
                current_level=3,
                available_schedule={f"{day}일차": 60 for day in range(7)},
            )

        self.assertEqual(len(fake_client.responses.calls), 2)


class WeeklyReviewPersistenceTests(unittest.TestCase):
    def test_plan_test_completion_forwards_plan_and_validates_response(self):
        expected = {
            "plan_id": PLAN_ID,
            "completed_task_count": 5,
            "task_exp": 50,
            "daily_bonus_exp": 20,
            "total_exp": 170,
            "level": 2,
            "current_streak": 3,
            "already_completed": False,
        }
        supabase = FakeRpcSupabase(expected)

        result = complete_study_plan_for_weekly_review_test(
            supabase,
            PLAN_ID,
        )

        self.assertEqual(result, expected)
        self.assertEqual(
            supabase.calls,
            [
                (
                    "complete_study_plan_for_weekly_review_test",
                    {"p_plan_id": PLAN_ID},
                )
            ],
        )

    def test_plan_test_completion_rejects_invalid_response(self):
        with self.assertRaises(RuntimeError):
            complete_study_plan_for_weekly_review_test(
                FakeRpcSupabase({"plan_id": PLAN_ID}),
                PLAN_ID,
            )

    def test_existing_review_is_updated_with_owner_filters(self):
        supabase = FakeSupabase()
        statistics = calculate_weekly_statistics(
            build_plan(),
            [build_task(status="completed")],
        )
        saved = update_weekly_review(
            supabase=supabase,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            review_id=REVIEW_ID,
            statistics=statistics,
            reflection_answers={"went_well": "계획 준수"},
            analysis=build_analysis(),
            markdown="## 이번 주 요약\n\n내용",
        )

        self.assertEqual(saved["id"], REVIEW_ID)
        self.assertEqual(supabase.request.operation, "update")
        self.assertEqual(
            supabase.request.filters,
            {"id": REVIEW_ID, "user_id": USER_ID, "plan_id": PLAN_ID},
        )

    def test_preview_state_does_not_mark_plan_saved(self):
        state = create_next_plan_draft_state(
            build_weekly_plan(),
            {"start_date": date(2026, 8, 21)},
        )
        self.assertIn(NEXT_PLAN_DRAFT_KEY, state)
        self.assertFalse(state[NEXT_PLAN_SAVED_KEY])
        self.assertIsNone(state[NEXT_PLAN_SAVED_ID_KEY])

    def test_state_reset_and_plan_change_preserve_other_features(self):
        state = {
            PLAN_SELECT_KEY: "new-plan",
            "weekly_review_active_plan_id": "old-plan",
            "weekly_review_next_plan_draft": {"title": "old"},
            "tutor_active_session_id": "keep-tutor",
            "saved_plan_selected_id": "keep-saved-plan",
        }

        self.assertTrue(apply_selected_plan_state(state, "new-plan"))
        self.assertEqual(state[PLAN_SELECT_KEY], "new-plan")
        self.assertNotIn("weekly_review_next_plan_draft", state)
        self.assertEqual(state["tutor_active_session_id"], "keep-tutor")

        clear_weekly_review_state(state)
        self.assertNotIn(PLAN_SELECT_KEY, state)
        self.assertEqual(state["saved_plan_selected_id"], "keep-saved-plan")

    def test_completion_navigation_selects_plan_without_touching_other_state(self):
        state = {"saved_plan_selected_id": "keep-saved-plan"}

        request_weekly_review_navigation(state, PLAN_ID)

        self.assertEqual(state[COMPLETED_PLAN_PENDING_KEY], PLAN_ID)
        self.assertEqual(state[PENDING_NAVIGATION_KEY], "주간 학습 회고")
        self.assertEqual(state["saved_plan_selected_id"], "keep-saved-plan")


if __name__ == "__main__":
    unittest.main()
