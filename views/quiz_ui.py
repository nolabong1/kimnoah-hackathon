from uuid import uuid4

import streamlit as st

from services.concept_mastery_repository import (
    get_quiz_attempt_analysis,
)
from services.learner_context_service import load_learner_context
from services.learning_objective_repository import (
    get_learning_objective_for_task,
)
from services.concept_service import (
    canonicalize_quiz_concepts,
    normalize_course_key,
)
from services.quiz_repository import (
    RECENT_QUIZ_ATTEMPT_LIMIT,
    get_learning_concept_catalog,
    get_quiz_by_task,
    get_quiz_attempts,
    has_perfect_current_quiz_attempt,
    save_quiz,
    submit_quiz_attempt,
)
from services.reference_material_service import (
    build_reference_material_options,
)
from services.review_material_repository import (
    get_learning_materials_by_plan,
    get_review_materials_by_plan,
)
from services.quiz_service import (
    MAX_QUIZ_REFERENCE_CHARS,
    generate_quiz,
    prepare_quiz_reference,
)
from views.gamification_state import queue_gamification_notifications
from views.interaction_state import queue_quiz_result_interaction
from views.error_feedback import (
    render_unexpected_error,
    render_unexpected_warning,
)
from views.operation_feedback import operation_status
from views.reference_material_state import get_reference_materials_snapshot
from views.study_plan_data_state import invalidate_study_task_snapshots
from views.spaced_review_ui import (
    get_spaced_review_label,
)


QUIZ_DIAGNOSIS_LABELS = {
    "concept_confusion": "개념 혼동",
    "condition_omission": "조건 누락",
    "procedure_error": "풀이 절차 오류",
    "calculation_error": "계산 오류",
    "boundary_error": "경계값 오류",
    "overgeneralization": "지나친 일반화",
    "representation_error": "표현 해석 오류",
    "other": "추가 점검 필요",
}


def _get_quiz_state_prefix(
    widget_scope: str,
    quiz_id: str,
) -> str:
    """화면과 퀴즈별로 겹치지 않는 상태 키 접두사를 만듭니다."""

    return f"{widget_scope}_quiz_attempt_{quiz_id}"


def _clear_quiz_answer_state(
    state_prefix: str,
    question_count: int,
) -> None:
    """다음 응시 전에 기존 객관식 답안 상태를 제거합니다."""

    for question_index in range(question_count):
        st.session_state.pop(
            f"{state_prefix}_answer_{question_index}",
            None,
        )

    st.session_state.pop(
        f"{state_prefix}_submission_request",
        None,
    )


def _is_current_quiz_attempt(
    attempt: dict,
    quiz: dict,
) -> bool:
    """응시 기록이 현재 퀴즈 버전에서 생성되었는지 확인합니다."""

    return (
        attempt.get("quiz_updated_at")
        == quiz.get("updated_at")
    )


def _get_display_questions(quiz: dict) -> list[dict] | None:
    """화면에 표시할 수 있는 기본 문항 구조인지 검사합니다."""

    questions = quiz.get("questions")

    if not isinstance(questions, list) or not questions:
        return None

    for question in questions:
        if not isinstance(question, dict):
            return None

        question_text = question.get("question")

        if (
            not isinstance(question_text, str)
            or not question_text.strip()
        ):
            return None

        choices = question.get("choices")

        if (
            not isinstance(choices, list)
            or len(choices) != 4
            or any(
                not isinstance(choice, str)
                or not choice.strip()
                for choice in choices
            )
        ):
            return None

    return questions


def _get_choice_diagnostic(
    question: dict,
    selected_index: int,
) -> dict | None:
    """새 문항의 선택지별 진단을 검증하고 과거 문항은 건너뜁니다."""

    choice_feedback = question.get("choice_feedback")
    if (
        not isinstance(choice_feedback, list)
        or len(choice_feedback) != 4
        or isinstance(selected_index, bool)
        or not isinstance(selected_index, int)
        or selected_index not in range(4)
    ):
        return None

    diagnostic = choice_feedback[selected_index]
    if not isinstance(diagnostic, dict):
        return None

    diagnosis_type = diagnostic.get("diagnosis_type")
    feedback = diagnostic.get("feedback")
    next_step = diagnostic.get("next_step")
    if (
        not isinstance(diagnosis_type, str)
        or diagnosis_type not in QUIZ_DIAGNOSIS_LABELS
        or not isinstance(feedback, str)
        or not feedback.strip()
        or not isinstance(next_step, str)
        or not next_step.strip()
    ):
        return None

    return {
        "label": QUIZ_DIAGNOSIS_LABELS[diagnosis_type],
        "feedback": feedback.strip(),
        "next_step": next_step.strip(),
    }


def _get_question_source_support(
    question: dict,
) -> dict[str, str] | None:
    """저장된 문항의 자료명과 근거 문장을 안전하게 꺼냅니다."""

    source_title = question.get("source_title")
    source_evidence = question.get("source_evidence")
    if (
        not isinstance(source_title, str)
        or not source_title.strip()
        or not isinstance(source_evidence, str)
        or not source_evidence.strip()
    ):
        return None
    return {
        "title": source_title.strip(),
        "evidence": source_evidence.strip(),
    }


def _render_adaptive_quiz_analysis(
    analysis: dict,
) -> None:
    """개념별 숙련도 변화와 연결된 자동 복습 일정을 표시합니다."""

    mastery_changes = analysis.get("mastery_changes", [])
    concept_masteries = analysis.get("concept_masteries", [])
    weak_concepts = analysis.get("weak_concepts", [])
    auto_review_tasks = analysis.get("auto_review_tasks", [])
    sections = (
        mastery_changes,
        concept_masteries,
        weak_concepts,
        auto_review_tasks,
    )
    if not all(isinstance(items, list) for items in sections):
        st.warning("저장된 개념 분석 결과 형식이 올바르지 않습니다.")
        return

    _render_concept_mastery_changes(
        mastery_changes=mastery_changes,
        concept_masteries=concept_masteries,
        weak_concepts=weak_concepts,
    )
    _render_attempt_weak_concepts(weak_concepts)
    _render_linked_auto_reviews(auto_review_tasks)


def _group_mastery_changes(
    mastery_changes: list[dict],
) -> dict[str, list[dict]]:
    """문항별 숙련도 변화를 개념 ID 단위로 묶습니다."""

    changes_by_concept: dict[str, list[dict]] = {}
    for change in mastery_changes:
        if not isinstance(change, dict):
            continue
        concept_id = change.get("concept_id")
        if isinstance(concept_id, str):
            changes_by_concept.setdefault(concept_id, []).append(change)
    return changes_by_concept


def _render_concept_mastery_changes(
    mastery_changes: list[dict],
    concept_masteries: list[dict],
    weak_concepts: list[dict],
) -> None:
    """이번 응시로 발생한 개념별 숙련도 변화 카드를 표시합니다."""

    st.markdown("#### 개념별 숙련도")
    if not concept_masteries:
        st.info("이 응시에는 분석할 수 있는 개념 태그가 없습니다.")
        return

    changes_by_concept = _group_mastery_changes(mastery_changes)
    weak_concept_ids = {
        concept.get("concept_id")
        for concept in weak_concepts
        if isinstance(concept, dict)
    }
    for mastery in concept_masteries:
        if not isinstance(mastery, dict):
            continue
        _render_concept_mastery_change(
            mastery=mastery,
            concept_changes=changes_by_concept.get(
                mastery.get("concept_id"),
                [],
            ),
            is_weak=mastery.get("concept_id") in weak_concept_ids,
        )


def _render_concept_mastery_change(
    mastery: dict,
    concept_changes: list[dict],
    is_weak: bool,
) -> None:
    """개념 하나의 현재 점수와 이번 응시 변화를 표시합니다."""

    score_delta = sum(
        change.get("score_delta", 0)
        for change in concept_changes
        if isinstance(change.get("score_delta"), int)
        and not isinstance(change.get("score_delta"), bool)
    )
    correct_count = sum(
        change.get("is_correct") is True for change in concept_changes
    )
    mastery_score = mastery.get("mastery_score", 0)
    score_before = (
        concept_changes[0].get("score_before")
        if concept_changes
        else mastery_score
    )
    score_after = (
        concept_changes[-1].get("score_after")
        if concept_changes
        else mastery_score
    )
    question_results = [
        f"{change.get('question_index', 0) + 1}번 "
        + ("정답" if change.get("is_correct") is True else "오답")
        for change in concept_changes
    ]

    with st.container(border=True):
        st.markdown(f"**{mastery.get('concept_name', '개념')}**")
        score_column, result_column = st.columns(2)
        score_column.metric(
            "현재 숙련도",
            f"{mastery_score}점",
            delta=f"{score_delta:+d}점",
            delta_description="이번 응시 변화",
        )
        result_column.metric(
            "이번 응시",
            f"{correct_count}/{len(concept_changes)}문항 정답",
        )
        st.progress(mastery_score, text=f"숙련도 {mastery_score}/100")
        if question_results:
            st.caption(
                f"이번 응시 숙련도: {score_before}점 → {score_after}점 · "
                "결과: " + ", ".join(question_results)
            )
        if is_weak:
            st.warning("현재 추가 복습이 필요한 취약 개념입니다.")


def _render_attempt_weak_concepts(weak_concepts: list[dict]) -> None:
    """이번 응시에서 확인된 취약 개념 목록을 표시합니다."""

    st.markdown("#### 이번 응시에서 확인된 취약 개념")
    if weak_concepts:
        for concept in weak_concepts:
            if not isinstance(concept, dict):
                continue

            st.warning(
                f"{concept.get('concept_name', '개념')} · "
                f"숙련도 {concept.get('mastery_score', 0)}점 · "
                "연속 오답 "
                f"{concept.get('consecutive_incorrect_count', 0)}회"
            )
    else:
        st.success(
            "이번 응시에서 현재 취약 기준에 해당하는 개념은 없습니다."
        )


def _render_linked_auto_reviews(auto_review_tasks: list[dict]) -> None:
    """이번 응시로 연결된 자동 복습 일정을 표시합니다."""

    st.markdown("#### 연결된 자동 복습 일정")
    if auto_review_tasks:
        for review_task in auto_review_tasks:
            if not isinstance(review_task, dict):
                continue

            with st.container(border=True):
                st.markdown(
                    f"**{review_task.get('title', '자동 복습')}**"
                )
                st.write(
                    "복습 예정일: "
                    f"{review_task.get('scheduled_date', '-')}"
                )
                st.caption(
                    f"{review_task.get('concept_name', '개념')} · "
                    f"예상 {review_task.get('estimated_minutes', 0)}분"
                )
                review_label = get_spaced_review_label(
                    {
                        **review_task,
                        "source_type": "weakness_review",
                    }
                )

                if review_label:
                    st.caption(review_label)
    else:
        st.info("이번 응시에 연결된 새 자동 복습 일정은 없습니다.")


def _render_quiz_answer_results(
    attempt: dict,
    questions: list[dict],
    answers: list[int],
) -> bool:
    """점수와 문항별 정오답·해설을 왼쪽 결과 영역에 표시합니다."""

    st.markdown(
        f"#### {attempt['attempt_number']}번째 응시 결과"
    )
    score_column, correct_column = st.columns(2)
    score_column.metric(
        "퀴즈 점수",
        f"{attempt['score']}점",
    )
    correct_column.metric(
        "정답 문항",
        f"{attempt['correct_count']}/"
        f"{attempt['total_questions']}",
    )

    for question_index, question in enumerate(questions):
        choices = question.get("choices")
        selected_index = answers[question_index]
        correct_index = question.get(
            "correct_answer_index"
        )

        if (
            not isinstance(choices, list)
            or len(choices) != 4
            or isinstance(selected_index, bool)
            or not isinstance(selected_index, int)
            or selected_index not in range(4)
            or isinstance(correct_index, bool)
            or not isinstance(correct_index, int)
            or correct_index not in range(4)
        ):
            st.error(
                "저장된 문항의 정답 형식이 "
                "올바르지 않습니다."
            )
            return False

        st.markdown(
            f"**{question_index + 1}. "
            f"{question.get('question', '')}**"
        )

        if selected_index == correct_index:
            st.success(
                f"정답 · {choices[correct_index]}"
            )
        else:
            st.error(
                f"내 답 · {choices[selected_index]}"
            )
            st.write(
                f"**정답:** {choices[correct_index]}"
            )
            diagnostic = _get_choice_diagnostic(
                question=question,
                selected_index=selected_index,
            )
            if diagnostic is not None:
                st.warning(
                    f"오답 유형 · {diagnostic['label']}"
                )
                st.write(
                    f"**선택한 답 점검:** {diagnostic['feedback']}"
                )
                st.caption(
                    f"다음 확인 · {diagnostic['next_step']}"
                )

        st.write(
            f"**해설:** "
            f"{question.get('explanation', '')}"
        )
        source_support = _get_question_source_support(question)
        if source_support is not None:
            with st.container(border=True):
                st.caption(
                    f"근거 자료 · {source_support['title']}"
                )
                st.markdown(
                    f"> {source_support['evidence']}"
                )

    return True


def _render_quiz_result(
    attempt: dict,
    analysis: dict | None,
) -> None:
    """퀴즈 결과와 적응형 학습 진단을 좌우 영역으로 표시합니다."""

    questions = attempt.get("questions_snapshot")
    answers = attempt.get("answers")

    if (
        not isinstance(questions, list)
        or not isinstance(answers, list)
        or len(questions) != len(answers)
    ):
        st.error(
            "저장된 퀴즈 응시 결과 형식이 올바르지 않습니다."
        )
        return

    display_questions = _get_display_questions(
        {
            "questions": questions,
        }
    )

    if display_questions is None:
        st.error(
            "저장된 퀴즈 응시 문항 형식이 올바르지 않습니다."
        )
        return

    result_column, diagnosis_column = st.columns(
        [1.65, 1],
        gap="large",
        vertical_alignment="top",
    )

    with result_column:
        result_is_valid = _render_quiz_answer_results(
            attempt=attempt,
            questions=display_questions,
            answers=answers,
        )

    if not result_is_valid:
        return

    with diagnosis_column:
        with st.container(border=True):
            st.markdown("### 학습 진단")
            st.caption("이번 응시를 기준으로 정리한 개념별 학습 상태입니다.")

            if analysis is None:
                st.info("표시할 개념별 학습 진단이 없습니다.")
            else:
                _render_adaptive_quiz_analysis(analysis)


def _render_quiz_form(
    supabase,
    quiz: dict,
    questions: list[dict],
    state_prefix: str,
    retake_state_key: str,
    feedback_state_key: str,
) -> None:
    """객관식 답안을 모아 서버 채점 RPC로 제출합니다."""

    answers = []

    with st.form(f"{state_prefix}_form"):
        for question_index, question in enumerate(questions):
            choices = question["choices"]

            st.markdown(
                f"**{question_index + 1}. "
                f"{question['question']}**"
            )

            selected_answer = st.radio(
                f"{question_index + 1}번 문항 답안",
                options=list(range(4)),
                index=None,
                format_func=(
                    lambda choice_index, choices=choices: (
                        choices[choice_index]
                    )
                ),
                key=(
                    f"{state_prefix}_answer_"
                    f"{question_index}"
                ),
                label_visibility="collapsed",
            )
            answers.append(selected_answer)

        submitted = st.form_submit_button(
            "답안 제출하기",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    if any(answer is None for answer in answers):
        st.warning("모든 문항에 답한 후 제출해주세요.")
        return

    _submit_quiz_answers(
        supabase=supabase,
        quiz=quiz,
        answers=answers,
        state_prefix=state_prefix,
        retake_state_key=retake_state_key,
        feedback_state_key=feedback_state_key,
    )


def _get_or_create_submission_request(
    existing_request: dict | None,
    quiz_updated_at: str,
    answers: list[int],
) -> dict:
    """같은 제출 재시도에는 기존 멱등 키를 재사용합니다."""

    if (
        isinstance(existing_request, dict)
        and existing_request.get("answers") == answers
        and existing_request.get("quiz_updated_at") == quiz_updated_at
        and isinstance(existing_request.get("submission_key"), str)
    ):
        return existing_request
    return {
        "submission_key": str(uuid4()),
        "quiz_updated_at": quiz_updated_at,
        "answers": answers,
    }


def _submit_quiz_answers(
    supabase,
    quiz: dict,
    answers: list[int],
    state_prefix: str,
    retake_state_key: str,
    feedback_state_key: str,
) -> None:
    """서버 채점 RPC를 호출하고 성공한 응시 상태만 갱신합니다."""

    request_state_key = f"{state_prefix}_submission_request"
    submission_request = _get_or_create_submission_request(
        existing_request=st.session_state.get(request_state_key),
        quiz_updated_at=quiz["updated_at"],
        answers=answers,
    )
    st.session_state[request_state_key] = submission_request

    try:
        with operation_status(
            "답안을 채점하고 있습니다...",
            "퀴즈 제출과 학습 진단을 완료했습니다",
            "퀴즈 제출 중 오류가 발생했습니다",
        ) as status:
            status.write("답안과 현재 퀴즈 버전을 확인합니다.")
            attempt = submit_quiz_attempt(
                supabase=supabase,
                quiz_id=quiz["id"],
                quiz_updated_at=quiz["updated_at"],
                answers=answers,
                submission_key=submission_request["submission_key"],
            )
            status.write("응시 기록·숙련도·자동 복습 결과를 저장했습니다.")

        queue_gamification_notifications(
            st.session_state,
            attempt.get("gamification"),
        )
        queue_quiz_result_interaction(
            st.session_state,
            attempt,
        )
        invalidate_study_task_snapshots(st.session_state)

        st.session_state.pop(request_state_key, None)
        st.session_state[retake_state_key] = False
        st.session_state[feedback_state_key] = (
            f"답안을 제출했습니다. 점수는 {attempt['score']}점입니다."
        )
        st.rerun()

    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.submit",
            user_message=(
                "퀴즈 제출에 실패했습니다. 잠시 후 다시 시도해주세요."
            ),
        )


def _render_quiz_completion_status(
    task: dict,
    quiz: dict | None,
    completion_unlocked: bool,
):
    """과제 완료 가능 조건을 표시할 상태 영역을 만듭니다."""

    completion_status = st.empty()
    if task.get("status") == "completed":
        return completion_status
    if completion_unlocked:
        completion_status.caption(
            "✅ 현재 퀴즈의 모든 문항을 맞혀 과제를 완료할 수 있습니다."
        )
    elif quiz is None:
        completion_status.caption(
            "🔒 퀴즈를 생성하고 모든 문항을 맞혀야 과제를 완료할 수 있습니다."
        )
    else:
        completion_status.caption(
            "🔒 현재 퀴즈의 모든 문항을 맞혀야 과제를 완료할 수 있습니다."
        )
    return completion_status


def _generate_quiz_for_task(
    supabase,
    user_id,
    plan_id,
    course_name,
    goal,
    current_level,
    task: dict,
    learning_objective,
    reference_material: dict | None = None,
) -> dict:
    """학습자 문맥을 반영한 퀴즈를 생성하고 현재 과제에 저장합니다."""

    course_key = normalize_course_key(course_name)
    concept_catalog = get_learning_concept_catalog(
        supabase=supabase,
        user_id=user_id,
        course_key=course_key,
    )
    learner_context = None
    try:
        learner_context = load_learner_context(
            supabase=supabase,
            user_id=user_id,
            course_name=course_name,
            course_key=course_key,
        )
    except Exception as error:
        render_unexpected_warning(
            error,
            operation="quiz.load_learner_context",
            user_message=(
                "최근 숙련도는 불러오지 못해 현재 계획과 과제 "
                "정보만으로 퀴즈를 생성합니다."
            ),
        )

    reference_title = (
        reference_material.get("title")
        if reference_material is not None
        else None
    )
    reference_content = (
        reference_material.get("content")
        if reference_material is not None
        else None
    )
    quiz_draft = generate_quiz(
        course_name=course_name,
        goal=goal,
        current_level=current_level,
        task_title=task["title"],
        task_description=task["description"],
        task_type=task["task_type"],
        estimated_minutes=task["estimated_minutes"],
        existing_concepts=concept_catalog,
        learner_context=learner_context,
        reference_title=reference_title,
        reference_content=reference_content,
        learning_objective=learning_objective,
    )
    quiz_draft = canonicalize_quiz_concepts(
        quiz=quiz_draft,
        concept_catalog=concept_catalog,
    )
    return save_quiz(
        supabase=supabase,
        user_id=user_id,
        plan_id=plan_id,
        task_id=task["id"],
        course_key=course_key,
        course_name=course_name,
        quiz=quiz_draft,
        reference_learning_material_id=(
            reference_material["id"]
            if reference_material is not None
            and reference_material["kind"] == "learning"
            else None
        ),
        reference_review_material_id=(
            reference_material["id"]
            if reference_material is not None
            and reference_material["kind"] == "review"
            else None
        ),
    )


def _render_quiz_reference_selector(
    supabase,
    user_id: str,
    plan_id: str,
    task_id: str,
    widget_scope: str,
    learning_objective_id: str,
) -> tuple[dict | None, bool]:
    """현재 계획의 저장 자료를 퀴즈 근거로 선택하고 검증합니다."""

    try:
        learning_materials, review_materials = (
            get_reference_materials_snapshot(
                supabase,
                user_id,
                plan_id,
                st.session_state,
                loader=lambda: (
                    get_learning_materials_by_plan(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                    ),
                    get_review_materials_by_plan(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                    ),
                ),
            )
        )
    except Exception as error:
        render_unexpected_warning(
            error,
            operation="quiz.load_reference_materials",
            user_message=(
                "저장된 참고자료를 불러오지 못해 지금은 퀴즈를 생성할 수 "
                "없습니다. 잠시 후 다시 시도해주세요."
            ),
        )
        return None, False

    material_by_key = build_reference_material_options(
        learning_materials=learning_materials,
        review_materials=review_materials,
        learning_objective_id=learning_objective_id,
    )
    if not material_by_key:
        st.caption(
            "이 학습목표에 연결된 원본 또는 AI 학습자료가 있으면 근거 기반 "
            "퀴즈를 만들 수 있습니다."
        )
        return None, True

    selection_key = (
        f"{widget_scope}_quiz_reference_{task_id}"
    )
    material_keys: list[str | None] = [None, *material_by_key]
    if st.session_state.get(selection_key) not in material_keys:
        st.session_state[selection_key] = None

    selected_material_key = st.selectbox(
        "퀴즈 근거 자료 (선택)",
        options=material_keys,
        format_func=lambda material_key: (
            "선택하지 않음 · 계획과 과제 정보만 사용"
            if material_key is None
            else material_by_key[material_key]["label"]
        ),
        key=selection_key,
        help=(
            "선택하면 문제와 정답, 해설을 해당 자료에서 확인할 수 있는 "
            "내용으로 제한합니다."
        ),
    )
    if selected_material_key is None:
        return None, True

    selected_material = material_by_key[selected_material_key]
    try:
        (
            reference_title,
            reference_content,
            reference_was_limited,
        ) = prepare_quiz_reference(
            reference_title=selected_material.get("title"),
            reference_content=selected_material.get("content"),
        )
    except ValueError as error:
        st.warning(str(error))
        return None, False

    if reference_was_limited:
        st.info(
            "자료가 길어 앞부분 "
            f"{MAX_QUIZ_REFERENCE_CHARS:,}자 이내만 이번 퀴즈의 근거로 "
            "사용합니다. 원본 자료 자체는 변경되지 않습니다."
        )
    else:
        st.caption(
            "선택한 자료에서 확인 가능한 내용만 사용하고, 결과 해설에 "
            "근거 문장을 함께 표시합니다."
        )

    return {
        **selected_material,
        "title": reference_title,
        "content": reference_content,
    }, True


def _render_quiz_generation_control(
    supabase,
    user_id,
    plan_id,
    course_name,
    goal,
    current_level,
    task: dict,
    widget_scope: str,
    quiz: dict | None,
    completion_unlocked: bool,
    completion_status,
) -> tuple[dict | None, bool]:
    """퀴즈 생성·재생성 버튼과 성공 후 세션 초기화를 처리합니다."""

    is_regeneration = quiz is not None
    if quiz is None:
        st.info(
            "아직 저장된 AI 퀴즈가 없습니다. "
            "과제 정보를 바탕으로 5문항 퀴즈를 생성할 수 있습니다."
        )
    else:
        objective_snapshot = quiz.get("objective_snapshot")
        if isinstance(objective_snapshot, dict):
            st.caption(
                "현재 퀴즈 목표 · "
                f"{objective_snapshot.get('title', '제목 없음')}"
            )
        elif quiz.get("learning_objective_id") is None:
            st.caption(
                "현재 저장된 퀴즈는 학습목표 연결 기능 도입 전 버전입니다."
            )

    try:
        learning_objective = get_learning_objective_for_task(
            supabase=supabase,
            user_id=user_id,
            plan_id=plan_id,
            task_id=str(task["id"]),
            learning_objective_id=(
                str(task["learning_objective_id"])
                if task.get("learning_objective_id")
                else None
            ),
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.load_learning_objective",
            user_message=(
                "퀴즈 과제의 학습목표를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return quiz, completion_unlocked
    if learning_objective is None:
        st.warning(
            "이 퀴즈 과제에 연결된 학습목표가 없습니다. 학습목표 migration "
            "적용 상태를 확인해주세요."
        )
        return quiz, completion_unlocked

    st.caption(
        f"{'다시 생성할 목표' if is_regeneration else '출제 목표'} · "
        f"{learning_objective.title}"
    )
    reference_material, reference_is_valid = _render_quiz_reference_selector(
        supabase=supabase,
        user_id=user_id,
        plan_id=plan_id,
        task_id=str(task["id"]),
        widget_scope=widget_scope,
        learning_objective_id=str(learning_objective.id),
    )

    button_label = (
        "AI 퀴즈 다시 생성하기"
        if is_regeneration
        else "AI 퀴즈 생성하기"
    )
    if not st.button(
        button_label,
        key=f"{widget_scope}_generate_quiz_{task['id']}",
        type="secondary" if is_regeneration else "primary",
        disabled=not reference_is_valid,
    ):
        return quiz, completion_unlocked

    try:
        with operation_status(
            "학습목표와 참고자료를 확인하고 있습니다...",
            "AI 퀴즈 생성과 저장을 완료했습니다",
            "AI 퀴즈 처리 중 오류가 발생했습니다",
        ) as status:
            status.write("출제 범위와 취약 개념 우선순위를 구성합니다.")
            quiz = _generate_quiz_for_task(
                supabase=supabase,
                user_id=user_id,
                plan_id=plan_id,
                course_name=course_name,
                goal=goal,
                current_level=current_level,
                task=task,
                learning_objective=learning_objective,
                reference_material=reference_material,
            )
            status.write("문항·정답·개념 연결을 검증해 저장했습니다.")

        completion_unlocked = False
        if task.get("status") != "completed":
            completion_status.caption(
                "🔒 현재 퀴즈의 모든 문항을 맞혀야 과제를 완료할 수 있습니다."
            )

        state_prefix = _get_quiz_state_prefix(
            widget_scope=widget_scope,
            quiz_id=quiz["id"],
        )
        _clear_quiz_answer_state(
            state_prefix=state_prefix,
            question_count=quiz["question_count"],
        )
        st.session_state[f"{state_prefix}_retake"] = True
    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.generate_and_save",
            user_message=(
                "AI 퀴즈 생성 또는 저장에 실패했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )

    return quiz, completion_unlocked


def _prepare_quiz_attempt_state(
    widget_scope: str,
    quiz: dict,
    questions: list[dict],
    attempts: list[dict],
) -> tuple[str, str, str, dict | None]:
    """현재 퀴즈 버전에 맞는 응시·초기화·피드백 상태를 준비합니다."""

    state_prefix = _get_quiz_state_prefix(
        widget_scope=widget_scope,
        quiz_id=quiz["id"],
    )
    retake_state_key = f"{state_prefix}_retake"
    reset_state_key = f"{state_prefix}_reset_answers"
    feedback_state_key = f"{state_prefix}_feedback"
    if st.session_state.pop(reset_state_key, False):
        _clear_quiz_answer_state(
            state_prefix=state_prefix,
            question_count=len(questions),
        )

    current_attempt = next(
        (
            attempt
            for attempt in attempts
            if _is_current_quiz_attempt(attempt=attempt, quiz=quiz)
        ),
        None,
    )
    st.session_state.setdefault(
        retake_state_key,
        current_attempt is None,
    )
    return (
        state_prefix,
        retake_state_key,
        feedback_state_key,
        current_attempt,
    )


def _render_quiz_attempt_content(
    supabase,
    user_id,
    plan_id,
    quiz: dict,
    widget_scope: str,
    completion_unlocked: bool,
) -> bool:
    """최근 응시 결과 또는 현재 버전의 응시 폼을 표시합니다."""

    try:
        attempts = get_quiz_attempts(
            supabase=supabase,
            user_id=user_id,
            quiz_id=quiz["id"],
            limit=RECENT_QUIZ_ATTEMPT_LIMIT,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.load_attempts",
            user_message=(
                "최근 퀴즈 응시 기록을 불러오지 못했습니다. 잠시 후 "
                "다시 시도해주세요."
            ),
        )
        return completion_unlocked

    st.markdown(f"### {quiz['title']}")
    st.caption(f"객관식 {quiz['question_count']}문항이 준비되었습니다.")
    questions = _get_display_questions(quiz)
    if questions is None:
        st.error("저장된 퀴즈 문항 형식이 올바르지 않습니다.")
        return False

    (
        state_prefix,
        retake_state_key,
        feedback_state_key,
        current_attempt,
    ) = _prepare_quiz_attempt_state(
        widget_scope=widget_scope,
        quiz=quiz,
        questions=questions,
        attempts=attempts,
    )

    feedback_message = st.session_state.pop(feedback_state_key, None)
    if feedback_message:
        st.success(feedback_message)

    if attempts:
        latest_attempt = attempts[0]
        attempt_count_label = (
            f"최근 {len(attempts)}회 기록"
            if len(attempts) == RECENT_QUIZ_ATTEMPT_LIMIT
            else f"총 {len(attempts)}회 응시"
        )
        st.caption(
            f"{attempt_count_label} · 최근 점수 {latest_attempt['score']}점"
        )

    if current_attempt is not None and not st.session_state[retake_state_key]:
        analysis = None
        try:
            analysis = get_quiz_attempt_analysis(
                supabase=supabase,
                user_id=user_id,
                plan_id=plan_id,
                quiz_attempt_id=current_attempt["id"],
            )
        except Exception as error:
            render_unexpected_warning(
                error,
                operation="quiz.load_attempt_analysis",
                user_message=(
                    "개념별 숙련도와 자동 복습 정보를 불러오지 "
                    "못했습니다. 퀴즈 결과만 표시합니다."
                ),
            )

        _render_quiz_result(attempt=current_attempt, analysis=analysis)
        if st.button("다시 응시하기", key=f"{state_prefix}_start_retake"):
            st.session_state[retake_state_key] = True
            st.session_state[f"{state_prefix}_reset_answers"] = True
            st.rerun()
        return completion_unlocked

    if attempts and current_attempt is None:
        st.info(
            "퀴즈가 새 문제로 갱신되었습니다. "
            "과거 응시 기록은 유지되며 현재 버전은 새로 응시할 수 있습니다."
        )

    _render_quiz_form(
        supabase=supabase,
        quiz=quiz,
        questions=questions,
        state_prefix=state_prefix,
        retake_state_key=retake_state_key,
        feedback_state_key=feedback_state_key,
    )
    return completion_unlocked


def _load_quiz_completion_state(
    supabase,
    user_id,
    task,
) -> tuple[dict | None, bool] | None:
    """저장된 퀴즈와 현재 버전의 완료 가능 상태를 불러옵니다."""

    try:
        quiz = get_quiz_by_task(
            supabase=supabase,
            user_id=user_id,
            task_id=task["id"],
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.load_for_task",
            user_message=(
                "저장된 AI 퀴즈를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return None

    if quiz is None:
        return None, False

    try:
        completion_unlocked = has_perfect_current_quiz_attempt(
            supabase=supabase,
            user_id=user_id,
            quiz_id=quiz["id"],
            quiz_updated_at=quiz["updated_at"],
            question_count=quiz["question_count"],
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="quiz.check_completion",
            user_message=(
                "퀴즈 완료 가능 여부를 불러오지 못했습니다. 잠시 후 "
                "다시 시도해주세요."
            ),
        )
        return None
    return quiz, completion_unlocked


def render_quiz_section(
    supabase,
    user_id,
    plan_id,
    course_name,
    goal,
    current_level,
    task,
    widget_scope,
    *,
    display_mode="toggle",
):
    """퀴즈 UI를 표시하고 현재 버전의 완료 가능 여부를 반환합니다."""

    if display_mode not in {"toggle", "open", "status_only"}:
        raise ValueError("지원하지 않는 AI 퀴즈 표시 방식입니다.")

    loaded_state = _load_quiz_completion_state(
        supabase=supabase,
        user_id=user_id,
        task=task,
    )
    if loaded_state is None:
        return False
    quiz, completion_unlocked = loaded_state

    completion_status = _render_quiz_completion_status(
        task=task,
        quiz=quiz,
        completion_unlocked=completion_unlocked,
    )

    if display_mode == "status_only":
        return completion_unlocked

    quiz_section_open = display_mode == "open"
    if display_mode == "toggle":
        quiz_section_open = st.toggle(
            "AI 퀴즈 열기",
            key=f"{widget_scope}_quiz_section_{task['id']}",
        )

    if not quiz_section_open:
        return completion_unlocked

    with st.container(border=True):
        quiz, completion_unlocked = _render_quiz_generation_control(
            supabase=supabase,
            user_id=user_id,
            plan_id=plan_id,
            course_name=course_name,
            goal=goal,
            current_level=current_level,
            task=task,
            widget_scope=widget_scope,
            quiz=quiz,
            completion_unlocked=completion_unlocked,
            completion_status=completion_status,
        )

        if quiz is None:
            return False
        return _render_quiz_attempt_content(
            supabase=supabase,
            user_id=user_id,
            plan_id=plan_id,
            quiz=quiz,
            widget_scope=widget_scope,
            completion_unlocked=completion_unlocked,
        )
