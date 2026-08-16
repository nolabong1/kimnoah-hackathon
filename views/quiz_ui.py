from uuid import uuid4

import streamlit as st

from services.concept_mastery_repository import (
    get_quiz_attempt_analysis,
)
from services.concept_service import (
    canonicalize_quiz_concepts,
    normalize_course_key,
)
from services.quiz_repository import (
    get_learning_concept_catalog,
    get_quiz_by_task,
    get_quiz_attempts,
    save_quiz,
    submit_quiz_attempt,
)
from services.quiz_service import generate_quiz
from views.spaced_review_ui import (
    get_spaced_review_label,
)


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


def _has_perfect_current_attempt(
    quiz: dict,
    attempts: list[dict],
) -> bool:
    """현재 퀴즈 버전에서 전 문항 정답 기록이 있는지 확인합니다."""

    question_count = quiz.get("question_count")

    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or question_count < 1
    ):
        return False

    return any(
        _is_current_quiz_attempt(
            attempt=attempt,
            quiz=quiz,
        )
        and attempt.get("correct_count") == question_count
        and attempt.get("total_questions") == question_count
        for attempt in attempts
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


def _render_adaptive_quiz_analysis(
    analysis: dict,
) -> None:
    """개념별 숙련도 변화와 연결된 자동 복습 일정을 표시합니다."""

    mastery_changes = analysis.get("mastery_changes", [])
    concept_masteries = analysis.get(
        "concept_masteries",
        [],
    )
    weak_concepts = analysis.get("weak_concepts", [])
    auto_review_tasks = analysis.get(
        "auto_review_tasks",
        [],
    )

    if not all(
        isinstance(items, list)
        for items in (
            mastery_changes,
            concept_masteries,
            weak_concepts,
            auto_review_tasks,
        )
    ):
        st.warning(
            "저장된 개념 분석 결과 형식이 올바르지 않습니다."
        )
        return

    st.markdown("#### 개념별 숙련도")

    if not concept_masteries:
        st.info(
            "이 응시에는 분석할 수 있는 개념 태그가 없습니다."
        )
    else:
        changes_by_concept: dict[str, list[dict]] = {}

        for change in mastery_changes:
            if not isinstance(change, dict):
                continue

            concept_id = change.get("concept_id")

            if isinstance(concept_id, str):
                changes_by_concept.setdefault(
                    concept_id,
                    [],
                ).append(change)

        weak_concept_ids = {
            concept.get("concept_id")
            for concept in weak_concepts
            if isinstance(concept, dict)
        }

        for mastery in concept_masteries:
            if not isinstance(mastery, dict):
                continue

            concept_id = mastery.get("concept_id")
            concept_changes = changes_by_concept.get(
                concept_id,
                [],
            )
            score_delta = sum(
                change.get("score_delta", 0)
                for change in concept_changes
                if isinstance(
                    change.get("score_delta"),
                    int,
                )
                and not isinstance(
                    change.get("score_delta"),
                    bool,
                )
            )
            correct_count = sum(
                change.get("is_correct") is True
                for change in concept_changes
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

            with st.container(border=True):
                st.markdown(
                    f"**{mastery.get('concept_name', '개념')}**"
                )

                score_column, result_column = st.columns(2)
                score_column.metric(
                    "현재 숙련도",
                    f"{mastery_score}점",
                    delta=f"{score_delta:+d}점",
                    delta_description="이번 응시 변화",
                )
                result_column.metric(
                    "이번 응시",
                    (
                        f"{correct_count}/"
                        f"{len(concept_changes)}문항 정답"
                    ),
                )
                st.progress(
                    mastery_score,
                    text=f"숙련도 {mastery_score}/100",
                )

                question_results = []

                for change in concept_changes:
                    question_number = (
                        change.get("question_index", 0) + 1
                    )
                    result_label = (
                        "정답"
                        if change.get("is_correct") is True
                        else "오답"
                    )
                    question_results.append(
                        f"{question_number}번 {result_label}"
                    )

                if question_results:
                    st.caption(
                        f"이번 응시 숙련도: {score_before}점 → "
                        f"{score_after}점 · 결과: "
                        + ", ".join(question_results)
                    )

                if concept_id in weak_concept_ids:
                    st.warning(
                        "현재 추가 복습이 필요한 취약 개념입니다."
                    )

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
            "이번 응시에서 현재 취약 기준에 해당하는 "
            "개념은 없습니다."
        )

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
        st.info(
            "이번 응시에 연결된 새 자동 복습 일정은 없습니다."
        )


def _render_quiz_result(
    attempt: dict,
    analysis: dict | None,
) -> None:
    """서버에 저장된 응시 점수와 문항별 해설을 표시합니다."""

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

    questions = display_questions

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
            return

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

        st.write(
            f"**해설:** "
            f"{question.get('explanation', '')}"
        )

    if analysis is not None:
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

    submission_request_state_key = (
        f"{state_prefix}_submission_request"
    )
    submission_request = st.session_state.get(
        submission_request_state_key
    )

    if (
        not isinstance(submission_request, dict)
        or submission_request.get("answers") != answers
        or submission_request.get("quiz_updated_at")
        != quiz["updated_at"]
    ):
        submission_request = {
            "submission_key": str(uuid4()),
            "quiz_updated_at": quiz["updated_at"],
            "answers": answers,
        }
        st.session_state[
            submission_request_state_key
        ] = submission_request

    submission_key = submission_request[
        "submission_key"
    ]

    try:
        with st.spinner(
            "답안을 채점하고 응시 기록을 저장하고 있습니다..."
        ):
            attempt = submit_quiz_attempt(
                supabase=supabase,
                quiz_id=quiz["id"],
                quiz_updated_at=quiz["updated_at"],
                answers=answers,
                submission_key=submission_key,
            )

        st.session_state.pop(
            submission_request_state_key,
            None,
        )
        st.session_state[retake_state_key] = False
        st.session_state[feedback_state_key] = (
            f"답안을 제출했습니다. "
            f"점수는 {attempt['score']}점입니다."
        )
        st.rerun()

    except Exception as error:
        st.error(
            f"퀴즈 제출에 실패했습니다: {error}"
        )


def render_quiz_section(
    supabase,
    user_id,
    plan_id,
    course_name,
    goal,
    current_level,
    task,
    widget_scope,
):
    """퀴즈 UI를 표시하고 현재 버전의 완료 가능 여부를 반환합니다."""

    try:
        quiz = get_quiz_by_task(
            supabase=supabase,
            user_id=user_id,
            task_id=task["id"],
        )

    except Exception as error:
        st.error(
            "저장된 AI 퀴즈를 불러오지 "
            f"못했습니다: {error}"
        )
        return False

    attempts = []

    if quiz is not None:
        try:
            attempts = get_quiz_attempts(
                supabase=supabase,
                user_id=user_id,
                quiz_id=quiz["id"],
            )

        except Exception as error:
            st.error(
                "퀴즈 응시 기록을 불러오지 "
                f"못했습니다: {error}"
            )
            return False

    completion_unlocked = (
        quiz is not None
        and _has_perfect_current_attempt(
            quiz=quiz,
            attempts=attempts,
        )
    )

    quiz_section_open = st.toggle(
        "AI 퀴즈 열기",
        key=(
            f"{widget_scope}_quiz_section_"
            f"{task['id']}"
        ),
    )

    completion_status = st.empty()

    if (
        task.get("status") != "completed"
        and completion_unlocked
    ):
        completion_status.caption(
            "✅ 현재 퀴즈의 모든 문항을 맞혀 "
            "과제를 완료할 수 있습니다."
        )
    elif (
        task.get("status") != "completed"
        and quiz is None
    ):
        completion_status.caption(
            "🔒 퀴즈를 생성하고 모든 문항을 맞혀야 "
            "과제를 완료할 수 있습니다."
        )
    elif task.get("status") != "completed":
        completion_status.caption(
            "🔒 현재 퀴즈의 모든 문항을 맞혀야 "
            "과제를 완료할 수 있습니다."
        )

    if not quiz_section_open:
        return completion_unlocked

    with st.container(border=True):
        is_regeneration = quiz is not None

        if quiz is None:
            st.info(
                "아직 저장된 AI 퀴즈가 없습니다. "
                "과제 정보를 바탕으로 5문항 퀴즈를 "
                "생성할 수 있습니다."
            )

        generate_button_label = (
            "AI 퀴즈 다시 생성하기"
            if is_regeneration
            else "AI 퀴즈 생성하기"
        )

        if st.button(
            generate_button_label,
            key=(
                f"{widget_scope}_generate_quiz_"
                f"{task['id']}"
            ),
            type=(
                "secondary"
                if is_regeneration
                else "primary"
            ),
        ):
            try:
                with st.spinner(
                    "과제에 맞는 AI 퀴즈를 "
                    "생성하고 저장하고 있습니다..."
                ):
                    course_key = normalize_course_key(
                        course_name
                    )
                    concept_catalog = (
                        get_learning_concept_catalog(
                            supabase=supabase,
                            user_id=user_id,
                            course_key=course_key,
                        )
                    )
                    quiz_draft = generate_quiz(
                        course_name=course_name,
                        goal=goal,
                        current_level=current_level,
                        task_title=task["title"],
                        task_description=task[
                            "description"
                        ],
                        task_type=task["task_type"],
                        estimated_minutes=task[
                            "estimated_minutes"
                        ],
                        existing_concepts=concept_catalog,
                    )
                    quiz_draft = canonicalize_quiz_concepts(
                        quiz=quiz_draft,
                        concept_catalog=concept_catalog,
                    )

                    quiz = save_quiz(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                        task_id=task["id"],
                        course_key=course_key,
                        course_name=course_name,
                        quiz=quiz_draft,
                    )

                completion_unlocked = False

                if task.get("status") != "completed":
                    completion_status.caption(
                        "🔒 현재 퀴즈의 모든 문항을 "
                        "맞혀야 과제를 완료할 수 있습니다."
                    )

                state_prefix = _get_quiz_state_prefix(
                    widget_scope=widget_scope,
                    quiz_id=quiz["id"],
                )
                _clear_quiz_answer_state(
                    state_prefix=state_prefix,
                    question_count=quiz["question_count"],
                )
                st.session_state[
                    f"{state_prefix}_retake"
                ] = True

                if is_regeneration:
                    st.success(
                        "AI 퀴즈를 새 문제로 "
                        "갱신했습니다."
                    )
                else:
                    st.success(
                        "AI 퀴즈를 생성하고 저장했습니다."
                    )

            except Exception as error:
                st.error(
                    "AI 퀴즈 생성 또는 저장에 "
                    f"실패했습니다: {error}"
                )

        if quiz is None:
            return False

        st.markdown(f"### {quiz['title']}")
        st.caption(
            f"객관식 {quiz['question_count']}문항이 "
            "준비되었습니다."
        )

        questions = _get_display_questions(quiz)

        if questions is None:
            st.error(
                "저장된 퀴즈 문항 형식이 올바르지 않습니다."
            )
            return False

        state_prefix = _get_quiz_state_prefix(
            widget_scope=widget_scope,
            quiz_id=quiz["id"],
        )
        retake_state_key = f"{state_prefix}_retake"
        reset_state_key = (
            f"{state_prefix}_reset_answers"
        )
        feedback_state_key = (
            f"{state_prefix}_feedback"
        )

        if st.session_state.pop(
            reset_state_key,
            False,
        ):
            _clear_quiz_answer_state(
                state_prefix=state_prefix,
                question_count=len(questions),
            )

        current_attempt = next(
            (
                attempt
                for attempt in attempts
                if _is_current_quiz_attempt(
                    attempt=attempt,
                    quiz=quiz,
                )
            ),
            None,
        )

        st.session_state.setdefault(
            retake_state_key,
            current_attempt is None,
        )

        feedback_message = st.session_state.pop(
            feedback_state_key,
            None,
        )

        if feedback_message:
            st.success(feedback_message)

        if attempts:
            latest_attempt = attempts[0]
            st.caption(
                f"총 {len(attempts)}회 응시 · "
                f"최근 점수 {latest_attempt['score']}점"
            )

        if (
            current_attempt is not None
            and not st.session_state[retake_state_key]
        ):
            analysis = None

            try:
                analysis = get_quiz_attempt_analysis(
                    supabase=supabase,
                    user_id=user_id,
                    plan_id=plan_id,
                    quiz_attempt_id=current_attempt["id"],
                )
            except Exception as error:
                st.warning(
                    "개념별 숙련도와 자동 복습 정보를 "
                    f"불러오지 못했습니다: {error}"
                )

            _render_quiz_result(
                attempt=current_attempt,
                analysis=analysis,
            )

            if st.button(
                "다시 응시하기",
                key=f"{state_prefix}_start_retake",
            ):
                st.session_state[retake_state_key] = True
                st.session_state[reset_state_key] = True
                st.rerun()

            return _has_perfect_current_attempt(
                quiz=quiz,
                attempts=attempts,
            )

        if attempts and current_attempt is None:
            st.info(
                "퀴즈가 새 문제로 갱신되었습니다. "
                "과거 응시 기록은 유지되며 현재 버전은 "
                "새로 응시할 수 있습니다."
            )

        _render_quiz_form(
            supabase=supabase,
            quiz=quiz,
            questions=questions,
            state_prefix=state_prefix,
            retake_state_key=retake_state_key,
            feedback_state_key=feedback_state_key,
        )

        return _has_perfect_current_attempt(
            quiz=quiz,
            attempts=attempts,
        )
