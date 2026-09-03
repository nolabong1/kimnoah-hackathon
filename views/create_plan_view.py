from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import save_weekly_study_plan
from services.study_plan_service import generate_weekly_study_plan
from views.error_feedback import render_unexpected_error
from views.operation_feedback import operation_status
from views.study_plan_data_state import (
    invalidate_learning_objective_snapshots,
    invalidate_study_plan_list_snapshot,
)
from views.ui_components import render_page_header


CURRENT_LEVEL_OPTIONS = {
    1: "처음 시작 · 관련 내용을 처음 배우는 단계",
    2: "입문 · 기본 용어를 조금 아는 단계",
    3: "기초 · 핵심 개념을 따라갈 수 있는 단계",
    4: "기초 활용 · 안내를 받으면 기본 문제를 푸는 단계",
    5: "보통 · 기본 문제를 스스로 해결하는 단계",
    6: "중급 · 익숙한 응용 문제를 해결하는 단계",
    7: "중상급 · 새로운 유형에도 개념을 적용하는 단계",
    8: "고급 · 복합 문제를 분석하고 해결하는 단계",
    9: "심화 · 어려운 문제를 효율적으로 해결하는 단계",
    10: "숙련 · 다른 사람에게 설명하고 확장하는 단계",
}


def render_create_plan(supabase, user):
    render_page_header(
        "계획 만들기",
        "현재 수준과 하루별 학습 가능 시간을 반영한 7일 계획을 만드세요.",
    )

    with st.container(border=True):
        st.subheader("1. 계획 조건")
        st.caption("과목과 목표를 구체적으로 입력할수록 계획이 선명해집니다.")

        with st.form("study_plan_form", border=False):
            course_name = st.text_input(
                "과목 또는 학습 주제",
                placeholder="예: 파이썬 기초",
                max_chars=100,
            )

            study_goal = st.text_area(
                "7일 학습 목표",
                placeholder=(
                    "예: 조건문과 반복문을 활용해 "
                    "간단한 프로그램 만들기"
                ),
                max_chars=1000,
            )

            level_column, date_column = st.columns(
                [1.7, 1],
                gap="large",
            )
            with level_column:
                current_level = st.selectbox(
                    "현재 수준 (1~10단계)",
                    options=list(CURRENT_LEVEL_OPTIONS),
                    index=1,
                    format_func=lambda level: (
                        f"{level}단계 · {CURRENT_LEVEL_OPTIONS[level]}"
                    ),
                    help=(
                        "현재 과목에 대한 자신의 수준과 가장 가까운 "
                        "단계를 선택하세요."
                    ),
                )
                st.caption(
                    "1단계는 처음 배우는 수준, "
                    "10단계는 설명하고 확장할 수 있는 수준입니다."
                )

            with date_column:
                start_date = st.date_input(
                    "학습 시작일",
                    value=datetime.now(
                        ZoneInfo("Asia/Seoul")
                    ).date(),
                )

            st.markdown("#### 2. 하루별 학습 가능 시간")
            st.caption(
                "단위는 분이며, 공부하지 않는 날은 0분으로 설정할 수 있습니다."
            )

            available_schedule = {}
            schedule_columns = st.columns(2)

            for day_offset in range(7):
                actual_date = start_date + timedelta(
                    days=day_offset
                )

                with schedule_columns[day_offset % 2]:
                    available_schedule[f"{day_offset}일차"] = (
                        st.number_input(
                            (
                                f"{day_offset + 1}일차 · "
                                f"{actual_date:%m/%d} (분)"
                            ),
                            min_value=0,
                            max_value=480,
                            value=60,
                            step=10,
                            key=(
                                f"available_minutes_"
                                f"{day_offset}"
                            ),
                        )
                    )

            plan_submitted = st.form_submit_button(
                "AI 학습계획 만들기",
                type="primary",
                icon=":material/auto_awesome:",
                width="stretch",
            )

    if plan_submitted:
        if not course_name.strip():
            st.warning(
                "과목 또는 학습 주제를 입력해주세요."
            )

        elif not study_goal.strip():
            st.warning("7일 학습 목표를 입력해주세요.")

        elif sum(available_schedule.values()) == 0:
            st.warning(
                "최소 하루 이상의 학습 시간을 입력해주세요."
            )

        else:
            try:
                with operation_status(
                    "현재 수준과 학습 가능 시간을 분석하고 있습니다...",
                    "7일 학습계획을 만들었습니다",
                    "학습계획 생성 중 오류가 발생했습니다",
                ) as status:
                    status.write("입력한 목표와 하루별 가능 시간을 확인합니다.")
                    generated_plan = (
                        generate_weekly_study_plan(
                            course_name=course_name.strip(),
                            goal=study_goal.strip(),
                            current_level=current_level,
                            available_schedule=(
                                available_schedule
                            ),
                        )
                    )
                    status.write("7일 과제 구성과 시간 제한을 검증했습니다.")

                st.session_state.generated_plan = (
                    generated_plan
                )
                st.session_state.generated_plan_start_date = (
                    start_date
                )
                st.session_state.generated_plan_metadata = {
                    "course_name": course_name.strip(),
                    "goal": study_goal.strip(),
                    "current_level": current_level,
                    "start_date": start_date,
                    "available_schedule": (
                        available_schedule
                    ),
                }
                st.session_state.generated_plan_saved = False
                st.session_state.pop(
                    "saved_plan_id",
                    None,
                )

            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="study_plan.generate",
                    user_message=(
                        "학습계획 생성에 실패했습니다. 입력 조건과 연결 "
                        "상태를 확인한 뒤 다시 시도해주세요."
                    ),
                )

    if "generated_plan" not in st.session_state:
        return

    plan = st.session_state.generated_plan
    plan_start_date = (
        st.session_state.generated_plan_start_date
    )

    task_type_names = {
        "learn": ":material/menu_book: 학습",
        "review": ":material/replay: 복습",
        "quiz": ":material/quiz: 퀴즈",
    }

    st.divider()
    st.subheader("3. AI 학습계획 미리보기")
    st.caption("내용을 확인한 뒤 아래 저장 영역에서 명시적으로 저장하세요.")

    with st.container(border=True):
        st.subheader(plan.title)

        st.info(
            f"**현재 수준 진단:** {plan.level_assessment}",
            icon=":material/psychology:",
        )
        st.write(f"**이번 주 목표:** {plan.weekly_goal}")
        st.write(f"**학습 전략:** {plan.strategy}")

        objective_titles = {
            objective.objective_key: objective.title
            for objective in plan.learning_objectives
        }
        st.markdown("#### 세부 학습목표")
        for objective in plan.learning_objectives:
            st.markdown(f"- **{objective.title}** — {objective.description}")

        for day in plan.days:
            actual_date = plan_start_date + timedelta(
                days=day.day_offset
            )

            with st.expander(
                f"{day.day_offset + 1}일차 · "
                f"{actual_date:%Y-%m-%d} · "
                f"{day.daily_focus}",
                expanded=day.day_offset == 0,
            ):
                if not day.tasks:
                    st.write("오늘은 휴식일입니다.")
                    continue

                for task in day.tasks:
                    task_name = task_type_names[
                        task.task_type
                    ]

                    st.markdown(
                        f"**{task_name} · {task.title}** "
                        f"— {task.estimated_minutes}분"
                    )
                    st.caption(
                        "연결 목표 · "
                        f"{objective_titles[task.objective_key]}"
                    )
                    st.write(task.description)

        st.success(
            plan.motivation_message,
            icon=":material/celebration:",
        )

    with st.container(border=True):
        st.subheader("4. 계획 저장")
        st.caption(
            "미리보기만으로는 저장되지 않습니다. "
            "내용을 확인한 뒤 저장 버튼을 눌러주세요."
        )

        if st.session_state.get(
            "generated_plan_saved",
            False,
        ):
            st.success(
                "이 학습계획은 Supabase에 저장되었습니다.",
                icon=":material/cloud_done:",
            )
            return

        if st.button(
            "이 계획 저장하기",
            type="primary",
            icon=":material/save:",
            width="stretch",
        ):
            metadata = (
                st.session_state.generated_plan_metadata
            )

            try:
                with operation_status(
                    "학습계획과 과제를 저장하고 있습니다...",
                    "학습계획 저장을 완료했습니다",
                    "학습계획 저장 중 오류가 발생했습니다",
                ) as status:
                    status.write("계획·학습목표·과제 소유권을 확인합니다.")
                    saved_plan = save_weekly_study_plan(
                        supabase=supabase,
                        user_id=user.id,
                        plan=plan,
                        course_name=metadata[
                            "course_name"
                        ],
                        goal=metadata["goal"],
                        current_level=metadata[
                            "current_level"
                        ],
                        start_date=metadata[
                            "start_date"
                        ],
                        available_schedule=metadata[
                            "available_schedule"
                        ],
                    )
                    invalidate_study_plan_list_snapshot(st.session_state)
                    invalidate_learning_objective_snapshots(st.session_state)
                    status.write(
                        "7일 계획과 연결 과제를 원자적으로 저장했습니다."
                    )

                st.session_state.generated_plan_saved = True
                st.session_state.saved_plan_id = (
                    saved_plan["id"]
                )
                st.rerun()

            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="study_plan.save",
                    user_message=(
                        "학습계획 저장에 실패했습니다. 잠시 후 다시 "
                        "시도해주세요."
                    ),
                )
