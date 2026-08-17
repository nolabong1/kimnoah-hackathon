from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from services.study_plan_repository import save_weekly_study_plan
from services.study_plan_service import generate_weekly_study_plan


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
    st.header("계획 만들기")
    st.caption(
        "현재 수준과 하루 학습 가능 시간을 반영합니다."
    )

    with st.form("study_plan_form"):
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

        start_date = st.date_input(
            "학습 시작일",
            value=datetime.now(
                ZoneInfo("Asia/Seoul")
            ).date(),
        )

        st.write("**하루 학습 가능 시간 (단위: 분)**")
        st.caption(
            "공부하지 않는 날은 0분으로 설정할 수 있습니다."
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
                with st.spinner(
                    "현재 수준을 분석하고 "
                    "7일 계획을 만들고 있습니다..."
                ):
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

                st.success(
                    "7일 학습계획이 생성되었습니다!"
                )

            except Exception as error:
                st.error(
                    f"학습계획 생성에 실패했습니다: {error}"
                )

    if "generated_plan" not in st.session_state:
        return

    plan = st.session_state.generated_plan
    plan_start_date = (
        st.session_state.generated_plan_start_date
    )

    task_type_names = {
        "learn": "📘 학습",
        "review": "🔁 복습",
        "quiz": "📝 퀴즈",
    }

    st.divider()
    st.header(plan.title)

    st.info(
        f"**현재 수준 진단:** {plan.level_assessment}"
    )
    st.write(f"**이번 주 목표:** {plan.weekly_goal}")
    st.write(f"**학습 전략:** {plan.strategy}")

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
                st.write(task.description)

    st.success(plan.motivation_message)

    if st.session_state.get(
        "generated_plan_saved",
        False,
    ):
        st.success(
            "이 학습계획은 Supabase에 저장되었습니다."
        )
        return

    if st.button(
        "이 계획 저장하기",
        type="primary",
        width="stretch",
    ):
        metadata = (
            st.session_state.generated_plan_metadata
        )

        try:
            with st.spinner(
                "학습계획과 과제를 저장하고 있습니다..."
            ):
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

            st.session_state.generated_plan_saved = True
            st.session_state.saved_plan_id = (
                saved_plan["id"]
            )
            st.rerun()

        except Exception as error:
            st.error(
                f"학습계획 저장에 실패했습니다: {error}"
            )
