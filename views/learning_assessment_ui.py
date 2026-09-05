import streamlit as st

from models.learning_assessment import (
    LearningAssessmentAttemptResult,
    LearningAssessmentFormState,
    LearningAssessmentPlanState,
)
from models.learning_objective import StoredLearningObjective
from services.learning_assessment_repository import (
    get_learning_assessment_state,
    save_learning_assessment_pair,
    submit_learning_assessment_attempt,
)
from services.learning_assessment_service import (
    generate_learning_assessment_pair,
)
from views.error_feedback import render_unexpected_error
from views.learning_assessment_state import (
    MESSAGE_KEY,
    clear_generated_assessment_pair,
    clear_submission_request,
    get_generated_assessment_pair,
    get_or_create_submission_request,
    store_generated_assessment_pair,
)
from views.operation_feedback import operation_status
from views.weekly_review_state import request_weekly_review_navigation


EVIDENCE_LABELS = {
    "explain": "개념 설명",
    "apply": "개념 적용",
    "differentiate": "오해 구분",
}


def _render_weekly_review_button(*, plan_id: str, widget_scope: str) -> None:
    """평가 비교가 불가능하거나 끝난 계획을 주간 회고로 연결합니다."""

    if st.button(
        "주간 회고로 이어가기",
        key=f"learning_assessment_weekly_review_{widget_scope}_{plan_id}",
        type="primary",
        icon=":material/arrow_forward:",
        width="stretch",
    ):
        request_weekly_review_navigation(st.session_state, plan_id)
        st.rerun()


def _objective_titles(form: LearningAssessmentFormState) -> dict[str, str]:
    """저장된 목표 스냅샷에서 화면 표시 제목을 구성합니다."""

    return {
        str(objective.get("objective_key")): str(
            objective.get("title") or objective.get("objective_key")
        )
        for objective in form.objective_snapshot
        if objective.get("objective_key")
    }


def _render_assessment_form(
    form: LearningAssessmentFormState,
) -> tuple[bool, list[int] | None]:
    """공식 평가 문항을 한 번에 제출하는 Streamlit form을 표시합니다."""

    if not form.questions:
        st.warning("현재 응시할 평가 문항을 불러오지 못했습니다.")
        return False, None

    objective_titles = _objective_titles(form)
    answer_values: list[int | None] = []
    with st.form(
        f"learning_assessment_form_{form.id}",
        border=False,
    ):
        current_objective_key = None
        for question_index, question in enumerate(form.questions):
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
                f"{EVIDENCE_LABELS[question.evidence_key]}"
            )
            answer_values.append(
                st.radio(
                    question.question,
                    options=list(range(4)),
                    index=None,
                    format_func=lambda index, choices=question.choices: (
                        choices[index]
                    ),
                    key=f"learning_assessment_answer_{form.id}_{question_index}",
                )
            )
        submitted = st.form_submit_button(
            "공식 평가 제출하기",
            type="primary",
            icon=":material/check_circle:",
            width="stretch",
        )

    if not submitted:
        return False, None
    if any(answer is None for answer in answer_values):
        st.warning("모든 문항에 답을 선택한 뒤 제출해주세요.")
        return False, None
    return True, [int(answer) for answer in answer_values if answer is not None]


def _render_assessment_result(
    form: LearningAssessmentFormState,
    attempt: LearningAssessmentAttemptResult,
) -> None:
    """저장된 공식 평가 점수와 문항별 근거를 표시합니다."""

    objective_titles = _objective_titles(form)
    st.metric(
        "공식 평가 점수",
        f"{attempt.score}점",
        help=(
            f"{attempt.total_questions}문항 중 "
            f"{attempt.correct_count}문항 정답"
        ),
    )
    score_columns = st.columns(2, gap="medium")
    for index, score in enumerate(attempt.objective_scores):
        with score_columns[index % 2]:
            with st.container(border=True):
                st.caption("세부 학습목표")
                st.metric(
                    objective_titles.get(score.objective_key, score.objective_key),
                    f"{score.score}점",
                )
                st.caption(
                    f"3문항 중 {score.correct_count}문항 정답"
                )

    if not form.questions:
        return
    with st.expander("문항별 결과와 해설"):
        for result in attempt.question_results:
            question = form.questions[result.question_index]
            result_icon = ":material/check_circle:" if result.is_correct else ":material/cancel:"
            st.markdown(
                f"**{result_icon} {result.question_index + 1}번 · "
                f"{EVIDENCE_LABELS[result.evidence_key]}**"
            )
            st.write(question.question)
            st.caption(
                "선택한 답 · "
                f"{question.choices[result.selected_answer_index]} | "
                "정답 · "
                f"{question.choices[result.correct_answer_index]}"
            )
            st.write(result.explanation)
            st.divider()


def _render_before_after_comparison(
    state: LearningAssessmentPlanState,
) -> None:
    """공식 사전·사후 평가의 동일 목표 점수 변화를 비교합니다."""

    pre_attempt = state.pre_attempt
    post_attempt = state.post_attempt
    post_form = state.post_assessment
    if pre_attempt is None or post_attempt is None or post_form is None:
        return

    st.markdown("### 학습 전·후 공식 비교")
    delta = post_attempt.score - pre_attempt.score
    metric_columns = st.columns(3, gap="medium")
    metric_columns[0].metric("사전 진단", f"{pre_attempt.score}점")
    metric_columns[1].metric("사후 평가", f"{post_attempt.score}점")
    metric_columns[2].metric("점수 변화", f"{delta:+d}점")

    pre_scores = {
        score.objective_key: score.score
        for score in pre_attempt.objective_scores
    }
    objective_titles = _objective_titles(post_form)
    with st.container(border=True):
        st.markdown("#### 학습목표별 변화")
        for post_score in post_attempt.objective_scores:
            pre_score = pre_scores.get(post_score.objective_key)
            if pre_score is None:
                continue
            objective_delta = post_score.score - pre_score
            st.markdown(
                f"- **{objective_titles.get(post_score.objective_key, post_score.objective_key)}** · "
                f"{pre_score}점 → {post_score.score}점 "
                f"({objective_delta:+d}점)"
            )
    st.caption(
        "동일한 학습목표와 성공 기준을 측정한 서로 다른 문항의 결과입니다. "
        "점수 변화는 관찰된 학습 결과이며 학습만의 인과효과를 단정하지 않습니다."
    )


def _generate_and_save_assessments(
    *,
    supabase,
    user_id: str,
    plan: dict,
    objectives: list[StoredLearningObjective],
) -> None:
    """평가 쌍을 한 번 생성하고 실패 시 같은 결과로 저장을 재시도합니다."""

    plan_id = str(plan["id"])
    pending = get_generated_assessment_pair(
        st.session_state,
        plan_id=plan_id,
    )
    if pending is None:
        generated = generate_learning_assessment_pair(
            course_name=str(plan["course_name"]),
            goal=str(plan["goal"]),
            current_level=int(plan["current_level"]),
            objectives=objectives,
        )
        pair_key = store_generated_assessment_pair(
            st.session_state,
            plan_id=plan_id,
            generated=generated,
        )
    else:
        generated, pair_key = pending

    save_learning_assessment_pair(
        supabase=supabase,
        user_id=user_id,
        plan_id=plan_id,
        pair_key=pair_key,
        generated=generated,
    )
    clear_generated_assessment_pair(st.session_state)


def _render_generation(
    *,
    supabase,
    user_id: str,
    plan: dict,
    objectives: list[StoredLearningObjective],
) -> None:
    """학습 시작 전 평가 쌍 생성 동작을 표시합니다."""

    pending = get_generated_assessment_pair(
        st.session_state,
        plan_id=str(plan["id"]),
    )
    button_label = (
        "평가 저장 다시 시도하기"
        if pending is not None
        else "사전·사후 평가 준비하기"
    )
    st.info(
        "계획의 세부 학습목표별 사전 진단과 사후 평가를 함께 준비합니다. "
        "사후 문항은 학습이 끝날 때까지 공개되지 않습니다.",
        icon=":material/assignment:",
    )
    if not st.button(
        button_label,
        key=f"learning_assessment_generate_{plan['id']}",
        type="primary",
        icon=":material/auto_awesome:",
        width="stretch",
    ):
        return
    try:
        with operation_status(
            "학습목표별 사전·사후 평가를 준비하고 있습니다...",
            "사전 진단 준비를 완료했습니다",
            "평가 준비 중 오류가 발생했습니다",
        ) as status:
            if pending is None:
                status.write("동일 기준의 서로 다른 두 평가를 생성합니다.")
            else:
                status.write("이미 생성된 평가를 다시 저장합니다.")
            _generate_and_save_assessments(
                supabase=supabase,
                user_id=user_id,
                plan=plan,
                objectives=objectives,
            )
            status.write("정답을 숨긴 공식 평가를 안전하게 저장했습니다.")
        st.session_state[MESSAGE_KEY] = "사전 진단이 준비되었습니다."
        st.rerun()
    except Exception as error:
        render_unexpected_error(
            error,
            operation="learning_assessment.generate_and_save",
            user_message=(
                "평가 준비에 실패했습니다. 생성이 끝난 뒤 저장만 실패했다면 "
                "같은 버튼으로 AI 재호출 없이 다시 저장할 수 있습니다."
            ),
        )


def _submit_assessment(
    *,
    supabase,
    user_id: str,
    form: LearningAssessmentFormState,
    answers: list[int],
) -> None:
    """동일 답안 재시도에 같은 키를 사용해 공식 평가를 제출합니다."""

    submission_key = get_or_create_submission_request(
        st.session_state,
        assessment_id=str(form.id),
        answers=answers,
    )
    submit_learning_assessment_attempt(
        supabase=supabase,
        user_id=user_id,
        assessment_id=str(form.id),
        answers=answers,
        submission_key=submission_key,
    )
    clear_submission_request(st.session_state, str(form.id))
    phase_label = "사전 진단" if form.phase == "pre" else "사후 평가"
    st.session_state[MESSAGE_KEY] = f"{phase_label} 결과를 저장했습니다."


def render_learning_assessment_section(
    *,
    supabase,
    user,
    plan: dict,
    objectives: list[StoredLearningObjective],
) -> None:
    """학습 성과 화면에 계획별 사전·사후 평가 흐름을 표시합니다."""

    st.subheader("학습 전·후 평가")
    st.caption(
        "계획 시작 전과 종료 후 같은 학습목표를 측정해 관찰된 변화를 비교합니다."
    )
    message = st.session_state.pop(MESSAGE_KEY, None)
    if message:
        st.success(message, icon=":material/check_circle:")

    try:
        state = get_learning_assessment_state(
            supabase=supabase,
            user_id=str(user.id),
            plan_id=str(plan["id"]),
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="learning_assessment.load_state",
            user_message=(
                "평가 기능을 불러오지 못했습니다. Supabase에 최신 평가 "
                "마이그레이션을 적용했는지 확인해주세요."
            ),
        )
        return

    with st.container(border=True):
        status_columns = st.columns(2, gap="medium")
        status_columns[0].metric(
            "사전 진단",
            "완료" if state.pre_attempt else "응시 전",
        )
        status_columns[1].metric(
            "사후 평가",
            "완료" if state.post_attempt else "대기",
        )

        if state.pre_assessment is None:
            if not 2 <= len(objectives) <= 5:
                st.info(
                    "이 계획에는 공식 평가에 필요한 2~5개의 세부 학습목표가 "
                    "없습니다. 새로 만든 계획부터 학습 전·후 평가를 사용할 수 있습니다."
                )
                if state.period_finished:
                    _render_weekly_review_button(
                        plan_id=str(plan["id"]),
                        widget_scope="legacy_objectives",
                    )
                return
            if state.can_generate:
                _render_generation(
                    supabase=supabase,
                    user_id=str(user.id),
                    plan=plan,
                    objectives=objectives,
                )
            else:
                st.info(
                    state.pre_reason
                    or "학습을 시작한 계획은 정식 사전 진단을 만들 수 없습니다."
                )
                if state.period_finished:
                    _render_weekly_review_button(
                        plan_id=str(plan["id"]),
                        widget_scope="without_pre",
                    )
            return

        if state.pre_attempt is None:
            if state.pre_eligible:
                st.markdown(f"### {state.pre_assessment.title}")
                submitted, answers = _render_assessment_form(
                    state.pre_assessment
                )
                if submitted and answers is not None:
                    try:
                        with operation_status(
                            "사전 진단을 채점하고 있습니다...",
                            "사전 진단을 저장했습니다",
                            "사전 진단 제출에 실패했습니다",
                        ):
                            _submit_assessment(
                                supabase=supabase,
                                user_id=str(user.id),
                                form=state.pre_assessment,
                                answers=answers,
                            )
                        st.rerun()
                    except Exception as error:
                        render_unexpected_error(
                            error,
                            operation="learning_assessment.submit_pre",
                            user_message=(
                                "사전 진단 제출에 실패했습니다. 같은 답안으로 "
                                "다시 제출하면 중복 저장되지 않습니다."
                            ),
                        )
            else:
                st.info(state.pre_reason or "현재 사전 진단에 응시할 수 없습니다.")
            return

        st.markdown("### 사전 진단 결과")
        _render_assessment_result(state.pre_assessment, state.pre_attempt)

        if state.post_attempt is None:
            if state.post_eligible and state.post_assessment is not None:
                st.divider()
                st.markdown(f"### {state.post_assessment.title}")
                submitted, answers = _render_assessment_form(
                    state.post_assessment
                )
                if submitted and answers is not None:
                    try:
                        with operation_status(
                            "사후 평가를 채점하고 있습니다...",
                            "사후 평가를 저장했습니다",
                            "사후 평가 제출에 실패했습니다",
                        ):
                            _submit_assessment(
                                supabase=supabase,
                                user_id=str(user.id),
                                form=state.post_assessment,
                                answers=answers,
                            )
                        st.rerun()
                    except Exception as error:
                        render_unexpected_error(
                            error,
                            operation="learning_assessment.submit_post",
                            user_message=(
                                "사후 평가 제출에 실패했습니다. 같은 답안으로 "
                                "다시 제출하면 중복 저장되지 않습니다."
                            ),
                        )
            else:
                st.info(state.post_reason or "사후 평가 응시 조건을 확인해주세요.")
            return

        if state.post_assessment is None:
            st.warning("저장된 사후 평가 정보를 불러오지 못했습니다.")
            return
        st.divider()
        st.markdown("### 사후 평가 결과")
        _render_assessment_result(state.post_assessment, state.post_attempt)
        st.divider()
        _render_before_after_comparison(state)

        _render_weekly_review_button(
            plan_id=str(plan["id"]),
            widget_scope="completed",
        )
