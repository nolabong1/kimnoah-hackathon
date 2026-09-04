import streamlit as st

from views.spaced_review_ui import get_spaced_review_label


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


def get_display_questions(quiz: dict) -> list[dict] | None:
    """화면에 표시할 수 있는 기본 문항 구조인지 검사합니다."""

    questions = quiz.get("questions")
    if not isinstance(questions, list) or not questions:
        return None

    for question in questions:
        if not isinstance(question, dict):
            return None
        question_text = question.get("question")
        if not isinstance(question_text, str) or not question_text.strip():
            return None
        choices = question.get("choices")
        if (
            not isinstance(choices, list)
            or len(choices) != 4
            or any(
                not isinstance(choice, str) or not choice.strip()
                for choice in choices
            )
        ):
            return None
    return questions


def get_choice_diagnostic(
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


def get_question_source_support(
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


def group_mastery_changes(
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


def _render_adaptive_quiz_analysis(analysis: dict) -> None:
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

    changes_by_concept = group_mastery_changes(mastery_changes)
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
        st.success("이번 응시에서 현재 취약 기준에 해당하는 개념은 없습니다.")


def _render_linked_auto_reviews(auto_review_tasks: list[dict]) -> None:
    """이번 응시로 연결된 자동 복습 일정을 표시합니다."""

    st.markdown("#### 연결된 자동 복습 일정")
    if auto_review_tasks:
        for review_task in auto_review_tasks:
            if not isinstance(review_task, dict):
                continue
            with st.container(border=True):
                st.markdown(f"**{review_task.get('title', '자동 복습')}**")
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

    st.markdown(f"#### {attempt['attempt_number']}번째 응시 결과")
    score_column, correct_column = st.columns(2)
    score_column.metric("퀴즈 점수", f"{attempt['score']}점")
    correct_column.metric(
        "정답 문항",
        f"{attempt['correct_count']}/{attempt['total_questions']}",
    )

    for question_index, question in enumerate(questions):
        choices = question.get("choices")
        selected_index = answers[question_index]
        correct_index = question.get("correct_answer_index")
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
            st.error("저장된 문항의 정답 형식이 올바르지 않습니다.")
            return False

        st.markdown(
            f"**{question_index + 1}. {question.get('question', '')}**"
        )
        if selected_index == correct_index:
            st.success(f"정답 · {choices[correct_index]}")
        else:
            st.error(f"내 답 · {choices[selected_index]}")
            st.write(f"**정답:** {choices[correct_index]}")
            diagnostic = get_choice_diagnostic(
                question=question,
                selected_index=selected_index,
            )
            if diagnostic is not None:
                st.warning(f"오답 유형 · {diagnostic['label']}")
                st.write(f"**선택한 답 점검:** {diagnostic['feedback']}")
                st.caption(f"다음 확인 · {diagnostic['next_step']}")

        st.write(f"**해설:** {question.get('explanation', '')}")
        source_support = get_question_source_support(question)
        if source_support is not None:
            with st.container(border=True):
                st.caption(f"근거 자료 · {source_support['title']}")
                st.markdown(f"> {source_support['evidence']}")
    return True


def render_quiz_result(
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
        st.error("저장된 퀴즈 응시 결과 형식이 올바르지 않습니다.")
        return

    display_questions = get_display_questions({"questions": questions})
    if display_questions is None:
        st.error("저장된 퀴즈 응시 문항 형식이 올바르지 않습니다.")
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
