from datetime import date, timedelta

import streamlit as st
from pydantic import ValidationError

from models.study_plan import WeeklyStudyPlan
from models.weekly_review import (
    WeeklyReviewAnalysis,
    WeeklyStatisticsSnapshot,
)
from services.study_plan_repository import (
    get_study_tasks_by_plan_ids,
    get_user_study_plans,
    save_weekly_study_plan,
)
from services.time_service import get_seoul_today
from services.study_plan_service import generate_weekly_study_plan
from services.weekly_review_repository import (
    create_weekly_review,
    get_weekly_review_by_plan,
    update_weekly_review,
)
from services.weekly_review_service import (
    MAX_REFLECTION_ANSWER_CHARS,
    REFLECTION_QUESTIONS,
    WeeklyReviewValidationError,
    build_weekly_review_context,
    calculate_weekly_statistics,
    convert_weekly_review_to_markdown,
    generate_weekly_review,
    get_default_next_plan_start_date,
    is_weekly_review_eligible,
    validate_reflection_answers,
)
from views.create_plan_view import CURRENT_LEVEL_OPTIONS
from views.error_feedback import render_unexpected_error
from views.operation_feedback import operation_status
from views.study_plan_data_state import (
    get_study_plan_list_snapshot,
    get_study_tasks_by_plan_ids_snapshot,
    invalidate_learning_objective_snapshots,
    invalidate_study_plan_list_snapshot,
)
from views.ui_components import (
    MetricItem,
    READING_CONTENT_WIDTH,
    content_frame,
    render_empty_state,
    render_metric_row,
    render_page_header,
)
from views.weekly_review_state import (
    COMPLETED_PLAN_PENDING_KEY,
    NEXT_PLAN_DRAFT_KEY,
    NEXT_PLAN_METADATA_KEY,
    NEXT_PLAN_RUNNING_KEY,
    NEXT_PLAN_SAVED_ID_KEY,
    NEXT_PLAN_SAVED_KEY,
    PENDING_NAVIGATION_KEY,
    PLAN_SELECT_KEY,
    REGENERATION_CONFIRM_KEY,
    REQUEST_RUNNING_KEY,
    SAVE_RUNNING_KEY,
    SAMPLE_REFLECTION_PENDING_KEY,
    SUCCESS_MESSAGE_KEY,
    TEST_COMPLETED_PLAN_PENDING_KEY,
    apply_selected_plan_state,
    clear_next_plan_draft,
    create_next_plan_draft_state,
)


NEXT_COURSE_KEY = "weekly_review_next_course_name"
NEXT_GOAL_KEY = "weekly_review_next_goal"
NEXT_START_DATE_KEY = "weekly_review_next_start_date"
NEXT_LEVEL_KEY = "weekly_review_next_current_level"
NEXT_SCORE_KEY = "weekly_review_next_recent_score"


def _seoul_today() -> date:
    """사용자 일일 기준인 서울 현재 날짜를 반환합니다."""

    return get_seoul_today()


def _is_missing_review_table_error(error: Exception) -> bool:
    """주간 회고 마이그레이션 미적용 오류인지 판정합니다."""

    error_text = str(error).casefold()
    return "weekly_learning_reviews" in error_text and any(
        marker in error_text
        for marker in ("pgrst", "schema cache", "does not exist", "could not find")
    )


def _reflection_widget_key(plan_id: str, answer_key: str) -> str:
    return f"weekly_review_reflection_{plan_id}_{answer_key}"


def _initialize_reflection_state(
    plan_id: str,
    saved_answers: dict | None,
) -> None:
    """저장 답변을 최초 위젯 생성 전에 세션 상태에 복원합니다."""

    for answer_key in REFLECTION_QUESTIONS:
        widget_key = _reflection_widget_key(plan_id, answer_key)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = str(
                (saved_answers or {}).get(answer_key, "") or ""
            )


def _collect_reflection_answers(plan_id: str) -> dict[str, str]:
    """현재 계획의 회고 위젯 값을 수집합니다."""

    return {
        answer_key: st.session_state.get(
            _reflection_widget_key(plan_id, answer_key),
            "",
        )
        for answer_key in REFLECTION_QUESTIONS
    }


def _render_statistics(statistics: WeeklyStatisticsSnapshot) -> None:
    """저장 스냅샷의 핵심 지표와 예정일별 내역을 표시합니다."""

    render_metric_row(
        [
            MetricItem("전체 과제", f"{statistics.total_tasks}개"),
            MetricItem("완료 과제", f"{statistics.completed_tasks}개"),
            MetricItem("완료율", f"{statistics.completion_rate:.1f}%"),
            MetricItem(
                "완료 기준 예상 학습량",
                f"{statistics.completed_estimated_minutes}분",
                help="완료된 과제에 설정된 예상 시간의 합계입니다.",
            ),
        ]
    )

    st.caption(
        f"예정된 학습일 {statistics.scheduled_study_days}일 · "
        f"완료 과제가 있는 날 {statistics.days_with_completed_task}일 · "
        f"전체 계획 분량 {statistics.total_planned_minutes}분"
    )
    type_counts = statistics.completed_by_task_type
    detail_columns = st.columns(2)
    with detail_columns[0]:
        with st.container(border=True):
            st.markdown("#### 상태별 과제")
            st.write(
                f"대기 {statistics.pending_tasks}개 · "
                f"건너뜀 {statistics.skipped_tasks}개"
            )
    with detail_columns[1]:
        with st.container(border=True):
            st.markdown("#### 유형별 완료")
            st.write(
                f"학습 {type_counts.get('learn', 0)}개 · "
                f"복습 {type_counts.get('review', 0)}개 · "
                f"퀴즈 {type_counts.get('quiz', 0)}개"
            )

    daily_rows = [
        {
            "예정일": scheduled_date,
            "완료 과제": statistics.task_completion_counts_by_date.get(
                scheduled_date,
                0,
            ),
            "완료 과제 기준 예상 학습량(분)": completed_minutes,
        }
        for scheduled_date, completed_minutes in (
            statistics.completed_estimated_minutes_by_date.items()
        )
    ]
    if daily_rows:
        st.dataframe(daily_rows, hide_index=True, width="stretch")
    else:
        render_empty_state(
            "저장된 과제가 없습니다",
            "이 계획의 통계는 0건으로 계산됩니다.",
            icon=":material/event_busy:",
        )


def _render_reflection_form(
    plan_id: str,
    existing_review: dict | None,
) -> bool:
    """네 가지 회고 질문을 표시하고 제출 여부를 반환합니다."""

    _initialize_reflection_state(
        plan_id,
        existing_review.get("reflection_answers") if existing_review else None,
    )
    with st.form(f"weekly_review_reflection_form_{plan_id}"):
        for answer_key, question in REFLECTION_QUESTIONS.items():
            st.text_area(
                question,
                max_chars=MAX_REFLECTION_ANSWER_CHARS,
                height=100,
                key=_reflection_widget_key(plan_id, answer_key),
            )
        return st.form_submit_button(
            "회고 다시 만들기" if existing_review else "AI 주간 회고 만들기",
            type="primary",
            icon=":material/auto_awesome:",
            disabled=st.session_state.get(REQUEST_RUNNING_KEY, False),
        )


def _generate_and_save_review(
    *,
    supabase,
    user_id: str,
    plan: dict,
    tasks: list[dict],
    existing_review: dict | None,
) -> None:
    """AI 회고를 한 번 생성하고 신규 저장 또는 명시적 갱신합니다."""

    if st.session_state.get(REQUEST_RUNNING_KEY, False):
        st.warning("이미 AI 주간 회고를 생성하고 있습니다.")
        return

    try:
        answers = validate_reflection_answers(
            _collect_reflection_answers(str(plan["id"]))
        )
        statistics = calculate_weekly_statistics(plan, tasks)
    except WeeklyReviewValidationError as error:
        st.warning(str(error))
        return

    st.session_state[REQUEST_RUNNING_KEY] = True
    try:
        with operation_status(
            "이번 주 학습 기록을 분석하고 있습니다...",
            "AI 주간 회고 생성과 저장을 완료했습니다",
            "AI 주간 회고 처리 중 오류가 발생했습니다",
        ) as status:
            status.write("과제 완료 통계와 작성한 회고 답변을 확인합니다.")
            analysis = generate_weekly_review(statistics, answers)
            status.write("분석 결과를 고정된 회고 문서 형식으로 변환합니다.")
            markdown = convert_weekly_review_to_markdown(analysis)
            status.write(
                "통계 스냅샷과 회고 내용을 기존 계획에 연결해 저장합니다."
            )
            if existing_review is None:
                create_weekly_review(
                    supabase=supabase,
                    user_id=user_id,
                    plan_id=str(plan["id"]),
                    statistics=statistics,
                    reflection_answers=answers,
                    analysis=analysis,
                    markdown=markdown,
                )
            else:
                update_weekly_review(
                    supabase=supabase,
                    user_id=user_id,
                    plan_id=str(plan["id"]),
                    review_id=str(existing_review["id"]),
                    statistics=statistics,
                    reflection_answers=answers,
                    analysis=analysis,
                    markdown=markdown,
                )
        st.session_state[SUCCESS_MESSAGE_KEY] = (
            "AI 주간 회고를 저장했습니다."
            if existing_review is None
            else "AI 주간 회고와 통계 스냅샷을 새로 갱신했습니다."
        )
        st.session_state[REGENERATION_CONFIRM_KEY] = False
        clear_next_plan_draft(st.session_state)
        st.rerun()
    except Exception as error:
        if _is_missing_review_table_error(error):
            user_message = (
                "주간 회고 테이블이 아직 없습니다. Supabase SQL Editor에서 "
                "supabase_weekly_learning_reviews.sql을 먼저 실행해주세요."
            )
        else:
            user_message = (
                "AI 주간 회고 생성 또는 저장에 실패했습니다. "
                "입력 내용과 연결 상태를 확인한 뒤 다시 시도해주세요."
            )
        render_unexpected_error(
            error,
            operation="weekly_review.generate_and_save",
            user_message=user_message,
        )
    finally:
        st.session_state[REQUEST_RUNNING_KEY] = False


def _render_existing_review(existing_review: dict) -> None:
    """저장된 Markdown 회고를 추가 API 호출 없이 표시합니다."""

    with content_frame(READING_CONTENT_WIDTH):
        st.markdown(existing_review["ai_review_markdown"])
        st.caption(
            f"저장 시점 통계 · {existing_review['week_start']} ~ "
            f"{existing_review['week_end']} · "
            f"갱신 {existing_review['updated_at']}"
        )


def _initialize_next_plan_inputs(
    plan: dict,
    analysis: WeeklyReviewAnalysis,
    today: date,
) -> None:
    """다음 계획 입력 위젯의 최초 기본값을 준비합니다."""

    st.session_state.setdefault(NEXT_COURSE_KEY, plan["course_name"])
    st.session_state.setdefault(NEXT_GOAL_KEY, analysis.recommended_next_goal)
    st.session_state.setdefault(
        NEXT_START_DATE_KEY,
        get_default_next_plan_start_date(plan["target_date"], today),
    )
    st.session_state.setdefault(NEXT_LEVEL_KEY, int(plan["current_level"]))
    st.session_state.setdefault(NEXT_SCORE_KEY, None)

    previous_schedule = plan.get("available_schedule") or {}
    for day_offset in range(7):
        schedule_key = f"weekly_review_next_minutes_{day_offset}"
        previous_minutes = previous_schedule.get(f"{day_offset}일차", 60)
        if not isinstance(previous_minutes, int) or not 0 <= previous_minutes <= 480:
            previous_minutes = 60
        st.session_state.setdefault(schedule_key, previous_minutes)


def _render_next_plan_preview(plan: WeeklyStudyPlan, start_date: date) -> None:
    """저장 전 7일 계획 전체를 표시합니다."""

    task_type_names = {
        "learn": "학습",
        "review": "복습",
        "quiz": "퀴즈",
    }
    st.subheader(plan.title)
    st.info(f"**현재 수준 진단:** {plan.level_assessment}")
    st.write(f"**다음 주 목표:** {plan.weekly_goal}")
    st.write(f"**학습전략:** {plan.strategy}")

    objective_titles = {
        objective.objective_key: objective.title
        for objective in plan.learning_objectives
    }
    st.markdown("#### 세부 학습목표")
    for objective in plan.learning_objectives:
        st.markdown(f"- **{objective.title}** — {objective.description}")

    for day_plan in plan.days:
        actual_date = start_date + timedelta(days=day_plan.day_offset)
        with st.expander(
            f"{day_plan.day_offset + 1}일차 · {actual_date:%Y-%m-%d} · "
            f"{day_plan.daily_focus}",
            expanded=day_plan.day_offset == 0,
        ):
            if not day_plan.tasks:
                st.write("오늘은 휴식일입니다.")
            for task in day_plan.tasks:
                st.markdown(
                    f"**{task_type_names[task.task_type]} · {task.title}** "
                    f"— {task.estimated_minutes}분"
                )
                st.caption(
                    "연결 목표 · "
                    f"{objective_titles[task.objective_key]}"
                )
                st.write(task.description)
    st.success(plan.motivation_message)


def _render_next_plan_section(
    *,
    supabase,
    user_id: str,
    plan: dict,
    existing_review: dict,
    today: date,
) -> None:
    """회고 문맥을 이용한 다음 7일 계획 생성·미리보기·저장을 처리합니다."""

    try:
        statistics = WeeklyStatisticsSnapshot.model_validate(
            existing_review["statistics_snapshot"]
        )
        analysis = WeeklyReviewAnalysis.model_validate(
            existing_review["ai_review_data"]
        )
        reflection_answers = validate_reflection_answers(
            existing_review["reflection_answers"]
        )
    except (ValidationError, WeeklyReviewValidationError, KeyError, TypeError):
        st.error("저장된 주간 회고 데이터가 올바르지 않아 다음 계획을 만들 수 없습니다.")
        return

    _initialize_next_plan_inputs(plan, analysis, today)
    draft_data = st.session_state.get(NEXT_PLAN_DRAFT_KEY)
    draft_exists = draft_data is not None

    with st.form(f"weekly_review_next_plan_form_{plan['id']}"):
        course_name = st.text_input(
            "과목 또는 학습 주제",
            max_chars=100,
            key=NEXT_COURSE_KEY,
        )
        next_goal = st.text_area(
            "다음 7일 학습 목표",
            max_chars=1000,
            key=NEXT_GOAL_KEY,
        )
        start_date = st.date_input(
            "다음 계획 시작일",
            key=NEXT_START_DATE_KEY,
            format="YYYY-MM-DD",
        )
        current_level = st.selectbox(
            "현재 수준 (1~10단계)",
            options=list(CURRENT_LEVEL_OPTIONS),
            format_func=lambda level: (
                f"{level}단계 · {CURRENT_LEVEL_OPTIONS[level]}"
            ),
            key=NEXT_LEVEL_KEY,
        )
        recent_score = st.number_input(
            "최근 평가점수 (선택)",
            min_value=0,
            max_value=100,
            step=1,
            placeholder="없으면 비워두세요.",
            key=NEXT_SCORE_KEY,
            help="이 값은 다음 계획 생성 참고용이며 계획 DB에는 저장하지 않습니다.",
        )

        st.write("**하루 학습 가능 시간 (단위: 분)**")
        schedule_columns = st.columns(2)
        available_schedule: dict[str, int] = {}
        for day_offset in range(7):
            actual_date = start_date + timedelta(days=day_offset)
            with schedule_columns[day_offset % 2]:
                available_schedule[f"{day_offset}일차"] = st.number_input(
                    f"{day_offset + 1}일차 · {actual_date:%m/%d} (분)",
                    min_value=0,
                    max_value=480,
                    step=10,
                    key=f"weekly_review_next_minutes_{day_offset}",
                )

        generation_submitted = st.form_submit_button(
            "계획 다시 생성하기" if draft_exists else "다음 주 계획 생성하기",
            type="primary",
            icon=":material/auto_awesome:",
            disabled=st.session_state.get(NEXT_PLAN_RUNNING_KEY, False),
        )

    if generation_submitted:
        if st.session_state.get(NEXT_PLAN_RUNNING_KEY, False):
            st.warning("이미 다음 주 계획을 생성하고 있습니다.")
        else:
            try:
                weekly_review_context = build_weekly_review_context(
                    statistics,
                    analysis,
                    reflection_answers,
                )
                st.session_state[NEXT_PLAN_RUNNING_KEY] = True
                with operation_status(
                    "주간 회고를 다음 계획 조건에 반영하고 있습니다...",
                    "다음 주 계획 미리보기를 만들었습니다",
                    "다음 주 계획 생성 중 오류가 발생했습니다",
                ) as status:
                    status.write("추천 목표와 학습량 조정 의견을 확인합니다.")
                    generated_plan = generate_weekly_study_plan(
                        course_name=course_name,
                        goal=next_goal,
                        current_level=current_level,
                        available_schedule=available_schedule,
                        weekly_review_context=weekly_review_context,
                        recent_score=recent_score,
                    )
                    status.write("7일 일정과 하루별 가능 시간을 검증했습니다.")
                metadata = {
                    "course_name": course_name.strip(),
                    "goal": next_goal.strip(),
                    "current_level": current_level,
                    "recent_score": recent_score,
                    "start_date": start_date,
                    "available_schedule": dict(available_schedule),
                }
                st.session_state.update(
                    create_next_plan_draft_state(generated_plan, metadata)
                )
                st.info("미리보기 상태이며 저장 버튼을 누르기 전에는 저장되지 않습니다.")
            except ValueError as error:
                st.warning(str(error))
            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="weekly_review.generate_next_plan",
                    user_message=(
                        "다음 주 계획 생성에 실패했습니다. 입력 조건과 "
                        "연결 상태를 확인한 뒤 다시 시도해주세요."
                    ),
                )
            finally:
                st.session_state[NEXT_PLAN_RUNNING_KEY] = False

    draft_data = st.session_state.get(NEXT_PLAN_DRAFT_KEY)
    if draft_data is None:
        return
    try:
        draft_plan = WeeklyStudyPlan.model_validate(draft_data)
        metadata = st.session_state[NEXT_PLAN_METADATA_KEY]
    except (ValidationError, KeyError, TypeError):
        st.error("다음 주 계획 미리보기 상태가 올바르지 않습니다. 다시 생성해주세요.")
        clear_next_plan_draft(st.session_state)
        return

    st.divider()
    st.caption("미리보기 · 저장 버튼을 누르기 전에는 Supabase에 추가되지 않습니다.")
    _render_next_plan_preview(draft_plan, metadata["start_date"])

    if st.session_state.get(NEXT_PLAN_SAVED_KEY, False):
        st.success("다음 주 계획을 저장했습니다.")
        if st.button(
            "저장된 계획에서 열기",
            key=f"weekly_review_open_saved_plan_{plan['id']}",
            icon=":material/open_in_new:",
        ):
            st.session_state[PENDING_NAVIGATION_KEY] = "저장된 계획"
            st.session_state["saved_plan_selected_id"] = st.session_state.get(
                NEXT_PLAN_SAVED_ID_KEY
            )
            st.rerun()
        return

    with st.container(horizontal=True):
        if st.button(
            "다음 주 계획 저장하기",
            key=f"weekly_review_save_next_plan_{plan['id']}",
            type="primary",
            disabled=st.session_state.get(SAVE_RUNNING_KEY, False),
        ):
            if st.session_state.get(SAVE_RUNNING_KEY, False):
                st.warning("이미 다음 주 계획을 저장하고 있습니다.")
            else:
                st.session_state[SAVE_RUNNING_KEY] = True
                try:
                    with operation_status(
                        "다음 주 계획과 과제를 저장하고 있습니다...",
                        "다음 주 계획 저장을 완료했습니다",
                        "다음 주 계획 저장 중 오류가 발생했습니다",
                    ) as status:
                        status.write("계획·학습목표·과제 연결을 확인합니다.")
                        saved_plan = save_weekly_study_plan(
                            supabase=supabase,
                            user_id=user_id,
                            plan=draft_plan,
                            course_name=metadata["course_name"],
                            goal=metadata["goal"],
                            current_level=metadata["current_level"],
                            start_date=metadata["start_date"],
                            available_schedule=metadata["available_schedule"],
                        )
                        invalidate_study_plan_list_snapshot(st.session_state)
                        invalidate_learning_objective_snapshots(
                            st.session_state
                        )
                        status.write("새 7일 계획을 원자적으로 저장했습니다.")
                    st.session_state[NEXT_PLAN_SAVED_KEY] = True
                    st.session_state[NEXT_PLAN_SAVED_ID_KEY] = saved_plan["id"]
                    st.rerun()
                except Exception as error:
                    render_unexpected_error(
                        error,
                        operation="weekly_review.save_next_plan",
                        user_message=(
                            "다음 주 계획 저장에 실패했습니다. 중복 저장 "
                            "여부를 확인한 뒤 다시 시도해주세요."
                        ),
                    )
                finally:
                    st.session_state[SAVE_RUNNING_KEY] = False

        if st.button(
            "조건 수정하기",
            key=f"weekly_review_edit_next_plan_{plan['id']}",
        ):
            clear_next_plan_draft(st.session_state)
            st.rerun()


def render_weekly_review(supabase, user) -> None:
    """완료 주간의 회고와 다음 7일 계획 생성 화면을 표시합니다."""

    user_id = str(user.id)
    today = _seoul_today()
    render_page_header(
        "주간 학습 회고",
        "완료한 계획의 기록과 나의 회고를 분석해 다음 7일을 설계합니다.",
    )
    st.caption("모든 날짜 판정은 Asia/Seoul 기준입니다.")
    st.session_state.setdefault(REQUEST_RUNNING_KEY, False)
    st.session_state.setdefault(NEXT_PLAN_RUNNING_KEY, False)
    st.session_state.setdefault(SAVE_RUNNING_KEY, False)

    if SUCCESS_MESSAGE_KEY in st.session_state:
        st.success(st.session_state.pop(SUCCESS_MESSAGE_KEY))

    try:
        plans = get_study_plan_list_snapshot(
            supabase,
            user_id,
            st.session_state,
            loader=lambda: get_user_study_plans(
                supabase=supabase,
                user_id=user_id,
            ),
        )
        tasks_by_plan = get_study_tasks_by_plan_ids_snapshot(
            supabase,
            user_id,
            [str(plan["id"]) for plan in plans],
            st.session_state,
            loader=lambda missing_plan_ids: get_study_tasks_by_plan_ids(
                supabase=supabase,
                user_id=user_id,
                plan_ids=missing_plan_ids,
            ),
        )
        eligible_entries = [
            (plan, tasks_by_plan.get(str(plan["id"]), []))
            for plan in plans
            if is_weekly_review_eligible(
                plan,
                tasks_by_plan.get(str(plan["id"]), []),
                today,
            )
        ]
    except Exception as error:
        render_unexpected_error(
            error,
            operation="weekly_review.load_eligible_plans",
            user_message=(
                "주간 회고 대상 계획을 불러오지 못했습니다. 잠시 후 "
                "다시 시도해주세요."
            ),
        )
        return

    if not plans:
        render_empty_state(
            "저장된 계획이 없습니다",
            "먼저 학습계획을 생성하고 저장해주세요.",
            icon=":material/calendar_add_on:",
        )
        return

    if not eligible_entries:
        render_empty_state(
            "아직 회고할 계획이 없습니다",
            "계획 종료일이 되었거나 모든 과제를 완료하면 이곳에 표시됩니다.",
            icon=":material/pending_actions:",
        )
        return

    entry_by_id = {
        str(plan["id"]): (plan, tasks)
        for plan, tasks in eligible_entries
    }
    eligible_plan_ids = list(entry_by_id)
    pending_completed_plan_id = st.session_state.pop(
        COMPLETED_PLAN_PENDING_KEY,
        None,
    )
    test_completed_plan_id = st.session_state.pop(
        TEST_COMPLETED_PLAN_PENDING_KEY,
        None,
    )
    if pending_completed_plan_id is None:
        pending_completed_plan_id = test_completed_plan_id
    if pending_completed_plan_id in eligible_plan_ids:
        st.session_state[PLAN_SELECT_KEY] = pending_completed_plan_id
    if st.session_state.get(PLAN_SELECT_KEY) not in eligible_plan_ids:
        st.session_state.pop(PLAN_SELECT_KEY, None)

    st.subheader("돌아볼 계획")
    selected_plan_id = st.selectbox(
        "회고할 계획",
        options=eligible_plan_ids,
        format_func=lambda plan_id: (
            f"{entry_by_id[plan_id][0]['title']} · "
            f"{entry_by_id[plan_id][0]['start_date']} ~ "
            f"{entry_by_id[plan_id][0]['target_date']}"
        ),
        key=PLAN_SELECT_KEY,
    )
    sample_reflection_answers = st.session_state.pop(
        SAMPLE_REFLECTION_PENDING_KEY,
        None,
    )
    apply_selected_plan_state(st.session_state, selected_plan_id)
    selected_plan, selected_tasks = entry_by_id[selected_plan_id]

    if isinstance(sample_reflection_answers, dict):
        for answer_key in REFLECTION_QUESTIONS:
            sample_answer = sample_reflection_answers.get(answer_key)
            if isinstance(sample_answer, str):
                st.session_state[
                    _reflection_widget_key(selected_plan_id, answer_key)
                ] = sample_answer

    try:
        existing_review = get_weekly_review_by_plan(
            supabase=supabase,
            user_id=user_id,
            plan_id=selected_plan_id,
        )
    except Exception as error:
        if _is_missing_review_table_error(error):
            user_message = (
                "주간 회고 테이블이 아직 없습니다. 프로젝트 루트의 "
                "supabase_weekly_learning_reviews.sql을 Supabase SQL Editor에서 "
                "한 번 실행해주세요."
            )
        else:
            user_message = (
                "저장된 주간 회고를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            )
        render_unexpected_error(
            error,
            operation="weekly_review.load_saved_review",
            user_message=user_message,
        )
        return

    try:
        statistics = (
            WeeklyStatisticsSnapshot.model_validate(
                existing_review["statistics_snapshot"]
            )
            if existing_review
            else calculate_weekly_statistics(selected_plan, selected_tasks)
        )
    except (ValidationError, WeeklyReviewValidationError, KeyError, TypeError):
        st.error("학습 기록 통계를 계산하거나 저장된 스냅샷을 읽지 못했습니다.")
        return

    status_text = (
        "모든 과제 완료"
        if statistics.total_tasks > 0
        and statistics.completed_tasks == statistics.total_tasks
        else "종료일 도달 · 미완료 과제 포함"
    )
    with st.container(border=True, horizontal=True):
        with st.container():
            st.caption("선택한 계획")
            st.markdown(f"### {statistics.plan_title}")
            st.caption(
                f"{statistics.course_name} · {statistics.plan_start_date} ~ "
                f"{statistics.plan_target_date}"
            )
        with st.container():
            st.caption("회고 가능 상태")
            st.markdown(f"### {status_text}")
            st.caption(
                f"완료 {statistics.completed_tasks}/{statistics.total_tasks}개"
            )

    st.info(
        "완료한 7일 계획은 여기서 끝나지 않습니다. "
        "**1. 기록과 나의 회고 → 2. AI 주간 회고 → "
        "3. 다음 7일 계획 생성·저장** 순서로 이어가세요.",
        icon=":material/route:",
    )
    if existing_review:
        st.success(
            "AI 주간 회고가 준비되어 있습니다. "
            "마지막 탭에서 다음 7일 계획을 이어서 만들 수 있습니다.",
            icon=":material/event_upcoming:",
        )

    record_tab, review_tab, next_plan_tab = st.tabs(
        ["1. 기록·나의 회고", "2. AI 주간 회고", "3. 다음 7일 계획"]
    )

    with record_tab:
        st.subheader("이번 주 학습 기록")
        if existing_review:
            st.caption(
                "저장된 회고의 통계 스냅샷입니다. 현재 과제 상태로 "
                "자동 덮어쓰지 않습니다."
            )
        _render_statistics(statistics)

        st.subheader("나의 회고")
        reflection_submitted = _render_reflection_form(
            selected_plan_id,
            existing_review,
        )
        if reflection_submitted:
            if existing_review is None:
                _generate_and_save_review(
                    supabase=supabase,
                    user_id=user_id,
                    plan=selected_plan,
                    tasks=selected_tasks,
                    existing_review=None,
                )
            else:
                try:
                    validate_reflection_answers(
                        _collect_reflection_answers(selected_plan_id)
                    )
                    st.session_state[REGENERATION_CONFIRM_KEY] = True
                    st.rerun()
                except WeeklyReviewValidationError as error:
                    st.warning(str(error))

        if existing_review and st.session_state.get(
            REGENERATION_CONFIRM_KEY,
            False,
        ):
            with st.container(border=True):
                st.warning(
                    "회고를 다시 만들면 현재 과제 상태로 통계를 다시 계산하고 "
                    "기존 회고를 갱신합니다. 계속할까요?"
                )
                with st.container(horizontal=True):
                    if st.button(
                        "다시 만들기 확인",
                        key=(
                            "weekly_review_confirm_regenerate_"
                            f"{selected_plan_id}"
                        ),
                        type="primary",
                    ):
                        _generate_and_save_review(
                            supabase=supabase,
                            user_id=user_id,
                            plan=selected_plan,
                            tasks=selected_tasks,
                            existing_review=existing_review,
                        )
                    if st.button(
                        "취소",
                        key=(
                            "weekly_review_cancel_regenerate_"
                            f"{selected_plan_id}"
                        ),
                    ):
                        st.session_state[REGENERATION_CONFIRM_KEY] = False
                        st.rerun()

    with review_tab:
        if existing_review is None:
            render_empty_state(
                "AI 회고가 아직 없습니다",
                "1단계에서 답변을 작성해 AI 주간 회고를 생성해주세요.",
                icon=":material/auto_awesome:",
            )
        else:
            _render_existing_review(existing_review)

    with next_plan_tab:
        if existing_review is None:
            render_empty_state(
                "다음 계획을 만들 준비가 필요합니다",
                "1단계의 회고를 작성하고 2단계의 AI 회고를 저장하면 "
                "다음 7일 계획을 만들 수 있습니다.",
                icon=":material/event_upcoming:",
            )
        else:
            _render_next_plan_section(
                supabase=supabase,
                user_id=user_id,
                plan=selected_plan,
                existing_review=existing_review,
                today=today,
            )
