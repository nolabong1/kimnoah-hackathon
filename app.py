import streamlit as st
from datetime import date, timedelta

from services.study_plan_service import generate_weekly_study_plan

from services.auth_service import sign_in, sign_out, sign_up
from services.supabase_client import get_supabase_client
from services.study_plan_repository import save_weekly_study_plan
from views.saved_plans_view import render_saved_plans


st.set_page_config(
    page_title="AI 학습 코치",
    page_icon="🎓",
    layout="centered",
)

supabase = get_supabase_client()

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


st.title("🎓 AI 학습 코치")
st.write("나의 목표와 수준에 맞는 학습계획을 만들어보세요.")


# 로그인하지 않은 사용자에게 인증 화면 표시
if st.session_state.auth_user is None:
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("이메일")
            login_password = st.text_input("비밀번호", type="password")
            login_submitted = st.form_submit_button("로그인")

        if login_submitted:
            try:
                response = sign_in(
                    supabase,
                    login_email,
                    login_password,
                )
                st.session_state.auth_user = response.user
                st.rerun()
            except Exception as error:
                st.error(f"로그인에 실패했습니다: {error}")

    with signup_tab:
        with st.form("signup_form"):
            nickname = st.text_input("닉네임", max_chars=30)
            signup_email = st.text_input("이메일")
            signup_password = st.text_input(
                "비밀번호",
                type="password",
                help="8자 이상 입력해주세요.",
            )
            password_confirm = st.text_input(
                "비밀번호 확인",
                type="password",
            )
            signup_submitted = st.form_submit_button("회원가입")

        if signup_submitted:
            if not nickname.strip():
                st.warning("닉네임을 입력해주세요.")
            elif "@" not in signup_email:
                st.warning("올바른 이메일을 입력해주세요.")
            elif len(signup_password) < 8:
                st.warning("비밀번호는 8자 이상이어야 합니다.")
            elif signup_password != password_confirm:
                st.warning("비밀번호가 일치하지 않습니다.")
            else:
                try:
                    response = sign_up(
                        supabase,
                        nickname,
                        signup_email,
                        signup_password,
                    )
                    st.session_state.auth_user = response.user
                    st.rerun()
                except Exception as error:
                    st.error(f"회원가입에 실패했습니다: {error}")

    st.stop()


# 로그인한 사용자의 프로필 조회
user = st.session_state.auth_user

try:
    profile_response = (
        supabase.table("profiles")
        .select("nickname, total_exp, level, current_streak")
        .eq("id", user.id)
        .single()
        .execute()
    )
    profile = profile_response.data
except Exception as error:
    st.error(f"프로필을 불러오지 못했습니다: {error}")
    st.stop()


with st.sidebar:
    st.write(f"**{profile['nickname']}**")
    st.metric("레벨", profile["level"])
    st.metric("총 EXP", profile["total_exp"])
    st.metric("연속 학습", f"{profile['current_streak']}일")

    if st.button("로그아웃"):
        sign_out(supabase)

        for key in [
            "generated_plan",
            "generated_plan_start_date",
            "generated_plan_metadata",
            "generated_plan_saved",
            "saved_plan_id",
        ]:
            st.session_state.pop(key, None)

        st.session_state.auth_user = None
        st.rerun()


st.success(f"{profile['nickname']}님, 환영합니다!")

st.subheader("나만의 7일 학습계획")
st.caption("현재 수준과 최근 점수, 하루 학습 가능 시간을 반영합니다.")

with st.form("study_plan_form"):
    course_name = st.text_input(
        "과목 또는 학습 주제",
        placeholder="예: 파이썬 기초",
        max_chars=100,
    )

    study_goal = st.text_area(
        "7일 학습 목표",
        placeholder="예: 조건문과 반복문을 활용해 간단한 프로그램 만들기",
        max_chars=1000,
    )

    current_level = st.slider(
        "현재 수준",
        min_value=1,
        max_value=5,
        value=2,
        help="1은 처음 배우는 단계, 5는 능숙한 단계입니다.",
    )

    recent_score = st.number_input(
        "최근 평가 점수",
        min_value=0,
        max_value=100,
        value=50,
        step=1,
        help="최근 퀴즈나 시험 점수를 입력하세요.",
    )

    start_date = st.date_input(
        "학습 시작일",
        value=date.today(),
    )

    st.write("**하루 학습 가능 시간**")
    st.caption("공부하지 않는 날은 0분으로 설정할 수 있습니다.")

    available_schedule = {}
    schedule_columns = st.columns(2)

    for day_offset in range(7):
        actual_date = start_date + timedelta(days=day_offset)

        with schedule_columns[day_offset % 2]:
            available_schedule[f"{day_offset}일차"] = st.number_input(
                f"{day_offset + 1}일차 · {actual_date:%m/%d}",
                min_value=0,
                max_value=480,
                value=60,
                step=10,
                key=f"available_minutes_{day_offset}",
            )

    plan_submitted = st.form_submit_button(
        "AI 학습계획 만들기",
        type="primary",
    )


if plan_submitted:
    if not course_name.strip():
        st.warning("과목 또는 학습 주제를 입력해주세요.")
    elif not study_goal.strip():
        st.warning("7일 학습 목표를 입력해주세요.")
    elif sum(available_schedule.values()) == 0:
        st.warning("최소 하루 이상의 학습 시간을 입력해주세요.")
    else:
        try:
            with st.spinner("현재 수준을 분석하고 7일 계획을 만들고 있습니다..."):
                generated_plan = generate_weekly_study_plan(
                    course_name=course_name.strip(),
                    goal=study_goal.strip(),
                    current_level=current_level,
                    recent_score=int(recent_score),
                    available_schedule=available_schedule,
                )

            st.session_state.generated_plan = generated_plan
            st.session_state.generated_plan_start_date = start_date
            st.session_state.generated_plan_metadata = {
                "course_name": course_name.strip(),
                "goal": study_goal.strip(),
                "current_level": current_level,
                "start_date": start_date,
                "available_schedule": available_schedule,
            }
            st.session_state.generated_plan_saved = False
            st.session_state.pop("saved_plan_id", None)

            st.success("7일 학습계획이 생성되었습니다!")

        except Exception as error:
            st.error(f"학습계획 생성에 실패했습니다: {error}")


if "generated_plan" in st.session_state:
    plan = st.session_state.generated_plan
    plan_start_date = st.session_state.generated_plan_start_date

    task_type_names = {
        "learn": "📘 학습",
        "review": "🔁 복습",
        "quiz": "📝 퀴즈",
    }

    st.divider()
    st.header(plan.title)

    st.info(f"**현재 수준 진단:** {plan.level_assessment}")
    st.write(f"**이번 주 목표:** {plan.weekly_goal}")
    st.write(f"**학습 전략:** {plan.strategy}")

    for day in plan.days:
        actual_date = plan_start_date + timedelta(days=day.day_offset)

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
                task_name = task_type_names[task.task_type]

                st.markdown(
                    f"**{task_name} · {task.title}** "
                    f"— {task.estimated_minutes}분"
                )
                st.write(task.description)

    st.success(plan.motivation_message)
    if st.session_state.get("generated_plan_saved", False):
        st.success("이 학습계획은 Supabase에 저장되었습니다.")

    elif st.button(
        "이 계획 저장하기",
        type="primary",
        use_container_width=True,
    ):
        metadata = st.session_state.generated_plan_metadata

        try:
            with st.spinner("학습계획과 과제를 저장하고 있습니다..."):
                saved_plan = save_weekly_study_plan(
                    supabase=supabase,
                    user_id=user.id,
                    plan=plan,
                    course_name=metadata["course_name"],
                    goal=metadata["goal"],
                    current_level=metadata["current_level"],
                    start_date=metadata["start_date"],
                    available_schedule=metadata["available_schedule"],
                )

            st.session_state.generated_plan_saved = True
            st.session_state.saved_plan_id = saved_plan["id"]
            st.rerun()

        except Exception as error:
            st.error(f"학습계획 저장에 실패했습니다: {error}")

render_saved_plans(
    supabase=supabase,
    user=user,
)