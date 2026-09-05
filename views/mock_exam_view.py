import streamlit as st

from models.mock_exam import MockExamAttemptResult, MockExamState
from services.learning_objective_repository import get_learning_objectives_by_plan_ids
from services.mock_exam_repository import (
    get_mock_exam_state,
    get_mock_exams_by_plan,
    save_mock_exam,
    submit_mock_exam_attempt,
)
from services.mock_exam_service import (
    MAX_MOCK_EXAM_REFERENCE_CHARS,
    generate_mock_exam,
)
from services.reference_material_service import build_reference_material_options
from services.study_plan_repository import get_user_study_plans
from views.error_feedback import render_unexpected_error
from views.mock_exam_state import (
    MESSAGE_KEY,
    SELECTED_EXAM_ID_KEY,
    clear_generated_mock_exam,
    clear_submission_request,
    get_generated_mock_exam,
    get_or_create_submission_request,
    store_generated_mock_exam,
)
from views.operation_feedback import operation_status
from views.reference_material_state import get_reference_materials_snapshot
from views.study_plan_data_state import (
    get_learning_objectives_by_plan_ids_snapshot,
    get_study_plan_list_snapshot,
)
from views.ui_components import MetricItem, render_empty_state, render_metric_row, render_page_header


PLAN_SELECT_KEY = "mock_exam_plan_id"
USE_REFERENCE_KEY = "mock_exam_use_reference"
REFERENCE_SELECT_KEY = "mock_exam_reference_key"
DIFFICULTY_LABELS = {
    "easy": "기초",
    "medium": "표준",
    "hard": "도전",
}
EVIDENCE_LABELS = {
    "explain": "개념 설명",
    "apply": "개념 적용",
    "differentiate": "오해 구분",
}


def _objective_titles(state: MockExamState) -> dict[str, str]:
    """저장된 목표 스냅샷에서 표시 제목을 구성합니다."""

    return {
        str(item.get("objective_key")): str(
            item.get("title") or item.get("objective_key")
        )
        for item in state.objective_snapshot
        if item.get("objective_key")
    }


def _render_attempt_result(
    state: MockExamState,
    attempt: MockExamAttemptResult,
) -> None:
    """최신 모의 평가 결과와 보완할 학습목표를 표시합니다."""

    objective_titles = _objective_titles(state)
    render_metric_row(
        [
            MetricItem(
                "최근 점수",
                f"{attempt.score}점",
                icon=":material/scoreboard:",
            ),
            MetricItem(
                "최고 점수",
                f"{state.best_score}점",
                icon=":material/emoji_events:",
            ),
            MetricItem(
                "정답",
                f"{attempt.correct_count}/15",
                icon=":material/check_circle:",
            ),
            MetricItem(
                "응시 횟수",
                f"{state.attempt_count}회",
                icon=":material/replay:",
            ),
        ]
    )
    if len(state.attempt_history) > 1:
        st.caption(
            "최근 점수 변화 · "
            + " → ".join(
                f"{item.attempt_number}회 {item.score}점"
                for item in state.attempt_history
            )
        )

    weak_scores = [
        score
        for score in attempt.objective_scores
        if score.score < 70
        or score.total_questions - score.correct_count >= 2
    ]
    st.markdown("### 학습목표별 결과")
    score_columns = st.columns(2, gap="medium")
    for index, score in enumerate(attempt.objective_scores):
        with score_columns[index % 2]:
            with st.container(border=True):
                st.metric(
                    objective_titles.get(score.objective_key, score.objective_key),
                    f"{score.score}점",
                )
                st.caption(
                    f"{score.total_questions}문항 중 "
                    f"{score.correct_count}문항 정답"
                )

    if weak_scores:
        with st.container(border=True):
            st.markdown("### :material/target: 이번에 보완할 영역")
            for score in weak_scores:
                st.markdown(
                    f"- **{objective_titles.get(score.objective_key, score.objective_key)}** · "
                    f"{score.score}점"
                )
            st.caption(
                "70점 미만이거나 두 문항 이상 틀린 학습목표입니다. "
                "연결된 복습자료를 다시 확인한 뒤 재응시해보세요."
            )
    else:
        st.success(
            "이번 응시에서는 별도로 표시할 보완 학습목표가 없습니다.",
            icon=":material/check_circle:",
        )

    with st.expander("문항별 정답과 해설"):
        for result in attempt.question_results:
            question = state.questions[result.question_index]
            icon = ":material/check_circle:" if result.is_correct else ":material/cancel:"
            st.markdown(
                f"**{icon} {result.question_index + 1}번 · "
                f"{EVIDENCE_LABELS[result.evidence_key]} · "
                f"{DIFFICULTY_LABELS[result.difficulty]}**"
            )
            st.write(question.question)
            st.caption(
                "선택한 답 · "
                f"{question.choices[result.selected_answer_index]} | "
                "정답 · "
                f"{question.choices[result.correct_answer_index]}"
            )
            st.write(result.explanation)
            if result.source_evidence:
                st.caption(
                    f"선택 자료 근거 · {result.source_title} · "
                    f"{result.source_evidence}"
                )
            st.divider()


def _render_exam_form(state: MockExamState) -> tuple[bool, list[int] | None]:
    """15문항을 한 번에 제출해 중간 rerun이 발생하지 않게 합니다."""

    answer_values: list[int | None] = [None] * len(state.questions)
    objective_titles = _objective_titles(state)
    with st.form(f"mock_exam_attempt_form_{state.exam_id}", border=False):
        page_tabs = st.tabs(["1~5번", "6~10번", "11~15번"])
        for page_index, page_tab in enumerate(page_tabs):
            with page_tab:
                current_objective_key = None
                start_index = page_index * 5
                for question_index in range(start_index, start_index + 5):
                    question = state.questions[question_index]
                    if question.objective_key != current_objective_key:
                        current_objective_key = question.objective_key
                        st.markdown(
                            "#### "
                            + objective_titles.get(
                                current_objective_key,
                                current_objective_key,
                            )
                        )
                    st.caption(
                        f"{question_index + 1}번 · "
                        f"{EVIDENCE_LABELS[question.evidence_key]} · "
                        f"{DIFFICULTY_LABELS[question.difficulty]}"
                    )
                    answer_values[question_index] = st.radio(
                        question.question,
                        options=list(range(4)),
                        index=None,
                        format_func=(
                            lambda index, choices=question.choices: choices[index]
                        ),
                        key=(
                            f"mock_exam_answer_{state.exam_id}_{question_index}"
                        ),
                    )
        submitted = st.form_submit_button(
            "모의 평가 제출하기",
            type="primary",
            icon=":material/check_circle:",
            width="stretch",
        )
    if not submitted:
        return False, None
    if any(answer is None for answer in answer_values):
        st.warning("15개 문항에 모두 답을 선택한 뒤 제출해주세요.")
        return False, None
    return True, [int(answer) for answer in answer_values if answer is not None]


def _generate_and_save_exam(
    *,
    supabase,
    user_id: str,
    plan: dict,
    objectives: list,
    reference_key: str | None,
    reference: dict | None,
) -> str:
    """AI 결과를 한 번 생성하고 저장 실패 시 같은 결과를 재사용합니다."""

    plan_id = str(plan["id"])
    pending = get_generated_mock_exam(
        st.session_state,
        plan_id=plan_id,
        reference_key=reference_key,
    )
    if pending is None:
        generated = generate_mock_exam(
            course_name=str(plan["course_name"]),
            goal=str(plan["goal"]),
            current_level=int(plan["current_level"]),
            objectives=objectives,
            reference_title=reference.get("title") if reference else None,
            reference_content=reference.get("content") if reference else None,
        )
        generation_key = store_generated_mock_exam(
            st.session_state,
            plan_id=plan_id,
            reference_key=reference_key,
            generated=generated,
        )
    else:
        generated, generation_key = pending

    result = save_mock_exam(
        supabase=supabase,
        user_id=user_id,
        plan_id=plan_id,
        generation_key=generation_key,
        generated=generated,
        reference_learning_material_id=(
            reference["id"] if reference and reference["kind"] == "learning" else None
        ),
        reference_review_material_id=(
            reference["id"] if reference and reference["kind"] == "review" else None
        ),
    )
    clear_generated_mock_exam(st.session_state)
    return str(result.id)


def _render_generation_panel(
    *,
    supabase,
    user,
    plan: dict,
    objectives: list,
) -> None:
    """새 모의 평가 생성 조건과 명시적 실행 버튼을 표시합니다."""

    plan_id = str(plan["id"])
    with st.container(border=True):
        st.markdown("### 새 문제 세트 만들기")
        st.caption(
            "계획의 모든 세부 학습목표를 균등하게 다루는 15문항을 생성합니다. "
            "AI 호출은 이 버튼을 누를 때만 발생합니다."
        )
        use_reference = st.checkbox(
            "저장된 자료를 참고해 출제하기",
            key=f"{USE_REFERENCE_KEY}_{plan_id}",
        )
        reference_options: dict[str, dict] = {}
        reference_key: str | None = None
        reference: dict | None = None
        if use_reference:
            try:
                learning_materials, review_materials = get_reference_materials_snapshot(
                    supabase,
                    str(user.id),
                    plan_id,
                    st.session_state,
                )
                reference_options = build_reference_material_options(
                    learning_materials,
                    review_materials,
                )
            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="mock_exam.load_references",
                    user_message="선택할 참고자료를 불러오지 못했습니다.",
                )
                return
            if not reference_options:
                st.info("이 계획에 저장된 원본 또는 AI 복습자료가 없습니다.")
            else:
                reference_key = st.selectbox(
                    "선택 참고자료",
                    options=list(reference_options),
                    format_func=lambda key: reference_options[key]["label"],
                    key=f"{REFERENCE_SELECT_KEY}_{plan_id}",
                )
                reference = reference_options[reference_key]
                if len(str(reference.get("content") or "")) > (
                    MAX_MOCK_EXAM_REFERENCE_CHARS
                ):
                    st.caption(
                        "긴 자료는 앞부분 최대 "
                        f"{MAX_MOCK_EXAM_REFERENCE_CHARS:,}자까지만 "
                        "결정론적으로 사용합니다."
                    )

        pending = get_generated_mock_exam(
            st.session_state,
            plan_id=plan_id,
            reference_key=reference_key,
        )
        button_label = (
            "모의 평가 저장 다시 시도하기"
            if pending is not None
            else "AI 모의 평가 만들기"
        )
        disabled = use_reference and not reference_options
        if not st.button(
            button_label,
            key=f"mock_exam_generate_{plan_id}",
            type="primary",
            icon=":material/auto_awesome:",
            width="stretch",
            disabled=disabled,
        ):
            return
        try:
            with operation_status(
                "시험 범위와 학습목표를 분석하고 있습니다...",
                "시험 대비 모의 평가를 저장했습니다",
                "모의 평가 생성 중 오류가 발생했습니다",
            ) as status:
                status.write("15문항의 목표·성공 기준·난이도를 균등 배분합니다.")
                exam_id = _generate_and_save_exam(
                    supabase=supabase,
                    user_id=str(user.id),
                    plan=plan,
                    objectives=objectives,
                    reference_key=reference_key,
                    reference=reference,
                )
                status.write("정답을 숨긴 문제 세트를 서버에 저장했습니다.")
            st.session_state[SELECTED_EXAM_ID_KEY] = exam_id
            st.session_state[MESSAGE_KEY] = "새 모의 평가가 준비되었습니다."
            st.rerun()
        except Exception as error:
            render_unexpected_error(
                error,
                operation="mock_exam.generate_and_save",
                user_message=(
                    "모의 평가 생성에 실패했습니다. 생성 후 저장만 실패했다면 "
                    "같은 조건으로 다시 눌러 AI 재호출 없이 저장할 수 있습니다."
                ),
            )


def _render_selected_exam(*, supabase, user, exam_id: str) -> None:
    """선택한 모의 평가의 최신 결과 또는 응시 폼을 렌더링합니다."""

    try:
        state = get_mock_exam_state(
            supabase=supabase,
            user_id=str(user.id),
            exam_id=exam_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="mock_exam.load_state",
            user_message="선택한 모의 평가를 불러오지 못했습니다.",
        )
        return

    st.subheader(state.title)
    st.caption(
        f"15문항 · 권장 {state.recommended_minutes}분 · "
        "시간은 안내용이며 자동 제출되지 않습니다."
    )
    retake_key = f"mock_exam_retaking_{state.exam_id}"
    is_retaking = bool(st.session_state.get(retake_key))
    if state.latest_attempt is not None and not is_retaking:
        _render_attempt_result(state, state.latest_attempt)
        if st.button(
            "같은 문제 다시 풀기",
            key=f"mock_exam_retake_{state.exam_id}",
            icon=":material/replay:",
            width="stretch",
        ):
            st.session_state[retake_key] = True
            st.rerun()
        return

    st.info(
        "제출 전에는 정답과 해설이 공개되지 않습니다. "
        "응시는 EXP, 과제 완료, 공식 사전·사후 평가에 영향을 주지 않습니다.",
        icon=":material/lock:"
    )
    submitted, answers = _render_exam_form(state)
    if not submitted or answers is None:
        return
    try:
        submission_key = get_or_create_submission_request(
            st.session_state,
            exam_id=str(state.exam_id),
            answers=answers,
        )
        with operation_status(
            "모의 평가를 채점하고 있습니다...",
            "모의 평가 결과를 저장했습니다",
            "모의 평가 제출에 실패했습니다",
        ):
            submit_mock_exam_attempt(
                supabase=supabase,
                user_id=str(user.id),
                exam_id=str(state.exam_id),
                answers=answers,
                submission_key=submission_key,
            )
        clear_submission_request(st.session_state, str(state.exam_id))
        st.session_state.pop(retake_key, None)
        st.session_state[MESSAGE_KEY] = "모의 평가 결과를 저장했습니다."
        st.rerun()
    except Exception as error:
        render_unexpected_error(
            error,
            operation="mock_exam.submit",
            user_message=(
                "모의 평가 제출에 실패했습니다. 같은 답안으로 다시 제출하면 "
                "중복 응시로 저장되지 않습니다."
            ),
        )


def render_mock_exam(supabase, user) -> None:
    """시험 대비 모의 평가 생성·응시·재응시 화면을 표시합니다."""

    render_page_header(
        "시험 대비 모의 평가",
        "계획 전체 범위를 15문항으로 점검하고 최근·최고 성적을 비교하세요.",
    )
    message = st.session_state.pop(MESSAGE_KEY, None)
    if message:
        st.success(message, icon=":material/check_circle:")

    try:
        plans = get_study_plan_list_snapshot(
            supabase,
            str(user.id),
            st.session_state,
            loader=lambda: get_user_study_plans(supabase, str(user.id)),
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="mock_exam.load_plans",
            user_message="모의 평가에 사용할 저장된 계획을 불러오지 못했습니다.",
        )
        return
    if not plans:
        render_empty_state(
            "저장된 학습계획이 없습니다",
            "먼저 7일 학습계획을 만든 뒤 시험 대비 모의 평가를 생성해주세요.",
            icon=":material/quiz:",
        )
        return

    plans_by_id = {str(plan["id"]): plan for plan in plans}
    plan_ids = list(plans_by_id)
    if st.session_state.get(PLAN_SELECT_KEY) not in plan_ids:
        st.session_state.pop(PLAN_SELECT_KEY, None)
    selected_plan_id = st.selectbox(
        "모의 평가를 만들 계획",
        options=plan_ids,
        format_func=lambda plan_id: (
            f"{plans_by_id[plan_id]['title']} · "
            f"{plans_by_id[plan_id]['course_name']}"
        ),
        key=PLAN_SELECT_KEY,
    )
    selected_plan = plans_by_id[selected_plan_id]

    try:
        objectives = get_learning_objectives_by_plan_ids_snapshot(
            supabase,
            str(user.id),
            [selected_plan_id],
            st.session_state,
            loader=lambda ids: get_learning_objectives_by_plan_ids(
                supabase,
                str(user.id),
                ids,
            ),
        )[selected_plan_id]
        exam_summaries = get_mock_exams_by_plan(
            supabase=supabase,
            user_id=str(user.id),
            plan_id=selected_plan_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="mock_exam.load_catalog",
            user_message=(
                "모의 평가 기능을 불러오지 못했습니다. Supabase에 최신 모의 "
                "평가 마이그레이션을 적용했는지 확인해주세요."
            ),
        )
        return

    if not 2 <= len(objectives) <= 5:
        render_empty_state(
            "모의 평가용 세부 학습목표가 없습니다",
            "2~5개의 세부 학습목표를 저장하는 새 학습계획부터 사용할 수 있습니다.",
            icon=":material/target:",
        )
        return

    _render_generation_panel(
        supabase=supabase,
        user=user,
        plan=selected_plan,
        objectives=objectives,
    )

    if not exam_summaries:
        st.info("아직 저장된 모의 평가가 없습니다. 새 문제 세트를 만들어보세요.")
        return
    summaries_by_id = {str(summary.id): summary for summary in exam_summaries}
    exam_ids = list(summaries_by_id)
    if st.session_state.get(SELECTED_EXAM_ID_KEY) not in exam_ids:
        st.session_state.pop(SELECTED_EXAM_ID_KEY, None)
    selected_exam_id = st.selectbox(
        "저장된 문제 세트",
        options=exam_ids,
        format_func=lambda exam_id: (
            f"{summaries_by_id[exam_id].title} · "
            f"최근 {summaries_by_id[exam_id].latest_score}점"
            if summaries_by_id[exam_id].latest_score is not None
            else f"{summaries_by_id[exam_id].title} · 미응시"
        ),
        key=SELECTED_EXAM_ID_KEY,
    )
    _render_selected_exam(
        supabase=supabase,
        user=user,
        exam_id=selected_exam_id,
    )
