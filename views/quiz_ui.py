import streamlit as st

from services.quiz_repository import (
    get_quiz_by_task,
    get_quiz_attempts,
    save_quiz,
    submit_quiz_attempt,
)
from services.quiz_service import generate_quiz


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


def _render_quiz_result(attempt: dict) -> None:
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

    st.success(
        f"{attempt['attempt_number']}번째 응시 결과 · "
        f"{attempt['score']}점 · "
        f"{attempt['correct_count']}/"
        f"{attempt['total_questions']}문항 정답"
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

    try:
        with st.spinner(
            "답안을 채점하고 응시 기록을 저장하고 있습니다..."
        ):
            attempt = submit_quiz_attempt(
                supabase=supabase,
                quiz_id=quiz["id"],
                quiz_updated_at=quiz["updated_at"],
                answers=answers,
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
                    )

                    quiz = save_quiz(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                        task_id=task["id"],
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
            _render_quiz_result(current_attempt)

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
