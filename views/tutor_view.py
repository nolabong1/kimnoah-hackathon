from uuid import uuid4

import streamlit as st
from pydantic import ValidationError

from models.tutor import (
    TutorAttemptFeedback,
    TutorGuidance,
)
from services.image_input_service import (
    MAX_IMAGE_COUNT,
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_TOTAL_IMAGE_UPLOAD_BYTES,
    ImageInputValidationError,
    prepare_images_for_ai,
    restore_prepared_images,
)
from services.review_material_repository import (
    get_learning_materials_by_plan,
    get_review_materials_by_plan,
)
from services.reference_material_service import (
    build_reference_material_options,
)
from services.study_plan_repository import (
    get_study_plan_tasks,
    get_user_study_plans,
)
from services.tutor_service import (
    MAX_TUTOR_ATTEMPT_CHARS,
    MAX_TUTOR_QUESTION_CHARS,
    MAX_TUTOR_REFERENCE_CHARS,
    TutorInputValidationError,
    generate_tutor_attempt_feedback,
    generate_tutor_guidance,
    validate_tutor_attempt,
    validate_tutor_problem_input,
)
from views.error_feedback import (
    render_unexpected_error,
    render_unexpected_warning,
)
from views.learning_context_state import (
    clear_learning_context,
    get_learning_context,
    has_learning_context,
)
from views.operation_feedback import operation_status
from views.reference_material_state import get_reference_materials_snapshot
from views.study_plan_data_state import (
    get_study_plan_list_snapshot,
    get_study_plan_tasks_snapshot,
)
from views.tutor_state import (
    ACTIVE_SESSION_ID_KEY,
    ACTIVE_USER_ID_KEY,
    COURSE_NAME_KEY,
    FEEDBACK_FINGERPRINT_KEY,
    FEEDBACK_IN_PROGRESS_KEY,
    FINAL_ANSWER_CONFIRMED_KEY,
    FINAL_CONFIRMATION_PENDING_KEY,
    GUIDANCE_KEY,
    LATEST_FEEDBACK_KEY,
    ORIGINAL_ATTEMPT_KEY,
    PROBLEM_IMAGES_KEY,
    QUESTION_KEY,
    REFERENCE_CONTEXT_KEY,
    REFERENCE_LIMITED_KEY,
    REFERENCE_TITLE_KEY,
    REQUEST_IN_PROGRESS_KEY,
    TASK_TITLE_KEY,
    VISIBLE_HINT_LEVEL_KEY,
    advance_hint_level,
    build_feedback_fingerprint,
    clear_tutor_state,
    create_tutor_session_state,
    get_visible_hints,
    is_final_solution_visible,
    previous_hint_level,
)
from views.ui_components import render_empty_state, render_page_header


SETUP_PLAN_KEY = "tutor_setup_plan_id"
SETUP_TASK_KEY = "tutor_setup_task_id"
SETUP_MATERIAL_KEY = "tutor_setup_material_key"
SETUP_QUESTION_KEY = "tutor_setup_question"
SETUP_ATTEMPT_KEY = "tutor_setup_attempt"
SETUP_IMAGES_KEY = "tutor_setup_problem_images"
REVISED_ATTEMPT_KEY = "tutor_revised_attempt"


def _clear_current_tutor() -> None:
    """콜백에서 현재 튜터 관련 상태만 안전하게 제거합니다."""

    clear_tutor_state(st.session_state)


def _start_pending_tutor_context() -> None:
    """전달받은 과제 문맥은 보존하고 기존 튜터 세션만 종료합니다."""

    clear_tutor_state(st.session_state)


def _get_context_source_label(source: str | None) -> str:
    """페이지 간 문맥 출처를 사용자용 짧은 이름으로 변환합니다."""

    if source == "today":
        return "오늘 학습"
    if source == "saved_plan":
        return "저장된 계획"
    return "이전 화면"


def _ensure_valid_widget_value(
    state_key: str,
    allowed_values: list[str | None],
) -> bool:
    """옵션 변경 후 남은 오래된 위젯 값을 생성 전에 정리합니다."""

    had_existing_value = state_key in st.session_state
    if st.session_state.get(state_key) not in allowed_values:
        st.session_state[state_key] = allowed_values[0]
        return had_existing_value
    return False


def _render_feedback(feedback_data: dict | None) -> None:
    """저장된 최신 풀이 피드백을 검증해 표시합니다."""

    if feedback_data is None:
        return
    try:
        feedback = TutorAttemptFeedback.model_validate(feedback_data)
    except ValidationError:
        st.warning("저장된 풀이 피드백을 표시할 수 없습니다.")
        return

    assessment_labels = {
        "correct": "핵심 접근이 적절합니다",
        "partially_correct": "일부 접근이 적절합니다",
        "needs_revision": "풀이를 조금 더 다듬어야 합니다",
        "insufficient_information": "판단할 풀이 정보가 부족합니다",
    }
    with st.container(border=True):
        st.markdown("### 풀이 점검 결과")
        st.write(assessment_labels[feedback.assessment])
        st.markdown(f"**잘한 점**\n\n{feedback.what_was_done_well}")
        st.markdown(f"**다시 볼 부분**\n\n{feedback.issue}")
        st.markdown(f"**다음 단계**\n\n{feedback.next_step}")
        st.caption(
            f"추천 힌트 단계: Hint {feedback.recommended_hint_level} · "
            "힌트 공개 여부는 직접 선택할 수 있습니다."
        )


def _render_final_solution(guidance: TutorGuidance) -> None:
    """명시적 확인 뒤 최종 정답과 풀이를 표시합니다."""

    solution = guidance.final_solution
    with st.container(border=True):
        st.markdown("## 최종 정답과 전체 풀이")
        st.markdown("### 최종 답")
        st.markdown(solution.final_answer)
        st.markdown("### 단계별 풀이")
        for index, step in enumerate(solution.reasoning_steps, start=1):
            st.markdown(f"{index}. {step}")
        st.markdown("### 풀이가 성립하는 이유")
        st.markdown(solution.why_solution_works)
        st.markdown("### 자주 하는 실수")
        for mistake in solution.common_mistakes:
            st.markdown(f"- {mistake}")
        st.markdown("### 짧은 자기 점검")
        st.info(solution.self_check_question)


@st.dialog("정답과 전체 풀이 확인")
def _render_final_answer_confirmation() -> None:
    """최종 답 공개 전 학습 종료 영향을 한 번 더 확인합니다."""

    st.warning(
        "정답과 전체 풀이를 확인하면 단계별 힌트 학습이 종료됩니다."
    )
    st.caption("과제 완료나 EXP 지급에는 영향을 주지 않습니다.")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "계속 풀어보기",
            key="tutor_cancel_answer_button",
        ):
            st.session_state[FINAL_CONFIRMATION_PENDING_KEY] = False
            st.rerun()
        if st.button(
            "정답 확인하기",
            key="tutor_confirm_answer_button",
            type="primary",
        ):
            st.session_state[FINAL_ANSWER_CONFIRMED_KEY] = True
            st.session_state[FINAL_CONFIRMATION_PENDING_KEY] = False
            st.rerun()


def _render_active_tutor_session(user_id: str) -> None:
    """저장된 안내로 힌트·피드백·정답 확인 UI를 렌더링합니다."""

    if st.session_state.get(ACTIVE_USER_ID_KEY) != user_id:
        clear_tutor_state(st.session_state)
        st.warning("현재 사용자와 다른 튜터 세션을 정리했습니다.")
        st.rerun()

    if has_learning_context(st.session_state):
        _plan_id, _task_id, context_source = get_learning_context(
            st.session_state
        )
        with st.container(border=True):
            st.info(
                f"{_get_context_source_label(context_source)}에서 다른 과제를 "
                "가져왔습니다. 현재 질문은 사용자가 전환하기 전까지 유지됩니다."
            )
            st.button(
                "가져온 과제로 새 질문 시작하기",
                key="tutor_start_pending_context_button",
                type="primary",
                icon=":material/swap_horiz:",
                on_click=_start_pending_tutor_context,
            )

    try:
        guidance = TutorGuidance.model_validate(
            st.session_state.get(GUIDANCE_KEY)
        )
    except ValidationError:
        st.error("진행 중인 튜터 세션을 복원하지 못했습니다.")
        st.button(
            "새 질문 시작하기",
            key="tutor_invalid_session_reset",
            on_click=_clear_current_tutor,
        )
        return

    try:
        problem_images = restore_prepared_images(
            st.session_state.get(PROBLEM_IMAGES_KEY)
        )
    except ImageInputValidationError:
        st.error("진행 중인 문제 이미지 세션을 복원하지 못했습니다.")
        st.button(
            "새 질문 시작하기",
            key="tutor_invalid_image_session_reset",
            on_click=_clear_current_tutor,
        )
        return

    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button(
            "새 질문 시작하기",
            key="tutor_new_question_button",
            icon=":material/restart_alt:",
            on_click=_clear_current_tutor,
        )

    st.caption(
        f"과목: {st.session_state[COURSE_NAME_KEY]} · "
        f"과제: {st.session_state.get(TASK_TITLE_KEY) or '직접 질문'}"
    )
    if st.session_state.get(REFERENCE_TITLE_KEY):
        st.caption(
            f"참고자료: {st.session_state[REFERENCE_TITLE_KEY]}"
        )
    if st.session_state.get(REFERENCE_LIMITED_KEY):
        st.info(
            "선택한 참고자료가 길어 앞부분 "
            f"최대 {MAX_TUTOR_REFERENCE_CHARS:,}자 범위만 튜터 문맥으로 "
            "사용했습니다."
        )

    context_columns = st.columns(2, gap="medium")
    with context_columns[0]:
        with st.container(border=True):
            st.caption("사용자 입력")
            st.markdown("### 내가 입력한 문제")
            st.write(st.session_state[QUESTION_KEY])
            if problem_images:
                st.caption(
                    f"첨부한 문제 이미지 {len(problem_images)}장 · "
                    "세션 종료 시 삭제"
                )
                image_columns = st.columns(min(2, len(problem_images)))
                for image_index, problem_image in enumerate(problem_images):
                    with image_columns[image_index % len(image_columns)]:
                        st.image(
                            problem_image.data_url,
                            caption=f"이미지 {image_index + 1}",
                            width="stretch",
                        )
            if st.session_state.get(ORIGINAL_ATTEMPT_KEY):
                st.markdown("**처음 시도한 풀이**")
                st.write(st.session_state[ORIGINAL_ATTEMPT_KEY])

    with context_columns[1]:
        with st.container(border=True):
            st.caption("튜터의 문제 해석")
            st.markdown("### 문제 이해")
            st.write(guidance.problem_summary)
            st.markdown("**필요한 개념**")
            st.markdown(
                "\n".join(
                    f"- {concept}"
                    for concept in guidance.required_concepts
                )
            )

    visible_hint_level = int(
        st.session_state.get(VISIBLE_HINT_LEVEL_KEY, 1)
    )
    visible_hints = get_visible_hints(guidance, visible_hint_level)
    st.subheader("단계별 힌트")
    hint_columns = st.columns(len(visible_hints), gap="medium")
    for hint_column, hint in zip(hint_columns, visible_hints):
        with hint_column:
            with st.container(border=True):
                st.caption(f"현재 공개 단계 · Hint {hint.level}")
                st.markdown(f"### {hint.title}")
                st.markdown(hint.content)
                st.info(f"생각해볼 질문: {hint.guiding_question}")

    if is_final_solution_visible(st.session_state):
        _render_final_solution(guidance)
        return

    with st.container(horizontal=True):
        if st.button(
            "이전 힌트",
            key="tutor_previous_hint_button",
            icon=":material/arrow_back:",
            disabled=visible_hint_level <= 1,
        ):
            st.session_state[VISIBLE_HINT_LEVEL_KEY] = previous_hint_level(
                visible_hint_level
            )
            st.rerun()

        if st.button(
            "다음 힌트",
            key="tutor_next_hint_button",
            icon=":material/arrow_forward:",
            disabled=visible_hint_level >= 3,
        ):
            st.session_state[VISIBLE_HINT_LEVEL_KEY] = advance_hint_level(
                visible_hint_level
            )
            st.rerun()

        if st.button(
            "정답 보기",
            key="tutor_show_answer_button",
            icon=":material/visibility:",
        ):
            st.session_state[FINAL_CONFIRMATION_PENDING_KEY] = True

    if st.session_state.get(FINAL_CONFIRMATION_PENDING_KEY):
        _render_final_answer_confirmation()

    st.subheader("수정한 풀이 점검하기")
    feedback_input_column, feedback_result_column = st.columns(
        2,
        gap="large",
        vertical_alignment="top",
    )
    with feedback_input_column:
        with st.container(border=True):
            with st.form("tutor_feedback_form"):
                revised_attempt = st.text_area(
                    "수정한 풀이",
                    height=180,
                    placeholder="힌트를 참고해 다시 시도한 풀이를 입력하세요.",
                    key=REVISED_ATTEMPT_KEY,
                )
                feedback_submitted = st.form_submit_button(
                    "내 풀이 점검하기",
                    key="tutor_feedback_submit",
                    icon=":material/rate_review:",
                    type="primary",
                    width="stretch",
                    disabled=bool(
                        st.session_state.get(
                            FEEDBACK_IN_PROGRESS_KEY,
                            False,
                        )
                    ),
                )

    if feedback_submitted:
        try:
            cleaned_revised_attempt = validate_tutor_attempt(
                revised_attempt,
                required=True,
            )
            fingerprint = build_feedback_fingerprint(
                session_id=st.session_state[ACTIVE_SESSION_ID_KEY],
                visible_hint_level=visible_hint_level,
                revised_attempt=cleaned_revised_attempt,
            )
            if (
                fingerprint
                == st.session_state.get(FEEDBACK_FINGERPRINT_KEY)
                and st.session_state.get(LATEST_FEEDBACK_KEY) is not None
            ):
                st.info("같은 풀이의 최근 점검 결과를 표시합니다.")
            else:
                st.session_state[FEEDBACK_IN_PROGRESS_KEY] = True
                with operation_status(
                    "수정한 풀이를 점검하고 있습니다...",
                    "풀이 점검을 완료했습니다",
                    "풀이 점검 중 오류가 발생했습니다",
                ) as status:
                    status.write("현재까지 공개된 힌트와 풀이를 비교합니다.")
                    feedback = generate_tutor_attempt_feedback(
                        course_name=st.session_state[COURSE_NAME_KEY],
                        task_title=st.session_state.get(TASK_TITLE_KEY),
                        reference_title=st.session_state.get(
                            REFERENCE_TITLE_KEY
                        ),
                        reference_context=st.session_state.get(
                            REFERENCE_CONTEXT_KEY
                        ),
                        question=st.session_state[QUESTION_KEY],
                        original_attempt=st.session_state.get(
                            ORIGINAL_ATTEMPT_KEY
                        ),
                        revised_attempt=cleaned_revised_attempt,
                        guidance=guidance,
                        revealed_hint_level=visible_hint_level,
                        problem_images=problem_images,
                    )
                    status.write("잘한 점과 다음에 시도할 단계를 정리했습니다.")
                st.session_state[LATEST_FEEDBACK_KEY] = feedback.model_dump()
                st.session_state[FEEDBACK_FINGERPRINT_KEY] = fingerprint
        except TutorInputValidationError as error:
            st.warning(str(error))
        except Exception as error:
            render_unexpected_error(
                error,
                operation="tutor.check_attempt",
                user_message=(
                    "풀이 점검 중 오류가 발생했습니다. 잠시 후 다시 "
                    "시도해주세요."
                ),
            )
        finally:
            st.session_state[FEEDBACK_IN_PROGRESS_KEY] = False

    with feedback_result_column:
        if st.session_state.get(LATEST_FEEDBACK_KEY) is None:
            render_empty_state(
                "풀이 점검 결과가 여기에 표시됩니다",
                "힌트를 참고해 수정한 풀이를 제출해보세요.",
                icon=":material/rate_review:",
            )
        else:
            _render_feedback(st.session_state.get(LATEST_FEEDBACK_KEY))


def _render_tutor_setup(supabase, user_id: str) -> None:
    """새 튜터 세션에 필요한 계획·과제·자료·질문을 입력받습니다."""

    try:
        study_plans = get_study_plan_list_snapshot(
            supabase,
            user_id,
            st.session_state,
            loader=lambda: get_user_study_plans(
                supabase=supabase,
                user_id=user_id,
            ),
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="tutor.load_plans",
            user_message=(
                "저장된 학습계획을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return
    if not study_plans:
        clear_learning_context(st.session_state)
        st.info("AI 튜터를 사용하려면 먼저 학습계획을 저장해주세요.")
        return

    plan_by_id = {str(plan["id"]): plan for plan in study_plans}
    plan_ids = list(plan_by_id)
    context_plan_id, context_task_id, context_source = get_learning_context(
        st.session_state
    )
    if context_plan_id is not None:
        if context_plan_id in plan_by_id:
            st.session_state[SETUP_PLAN_KEY] = context_plan_id
        else:
            clear_learning_context(st.session_state)
            context_plan_id = None
            context_task_id = None
            st.warning(
                "이전 화면에서 가져온 학습계획을 찾을 수 없습니다. "
                "본인의 저장된 계획을 다시 선택해주세요."
            )
    if _ensure_valid_widget_value(SETUP_PLAN_KEY, plan_ids):
        st.warning(
            "이전에 선택한 계획을 찾을 수 없어 다른 저장 계획을 표시합니다."
        )
    with st.container(border=True):
        st.subheader("튜터 학습 맥락")
        selected_plan_id = st.selectbox(
            "학습계획",
            options=plan_ids,
            format_func=lambda plan_id: (
                f"{plan_by_id[plan_id]['title']} · "
                f"{plan_by_id[plan_id]['course_name']}"
            ),
            key=SETUP_PLAN_KEY,
        )

    try:
        tasks = get_study_plan_tasks_snapshot(
            supabase,
            user_id,
            selected_plan_id,
            st.session_state,
            loader=lambda: get_study_plan_tasks(
                supabase=supabase,
                user_id=user_id,
                plan_id=selected_plan_id,
            ),
        )
    except Exception as error:
        tasks = []
        render_unexpected_warning(
            error,
            operation="tutor.load_tasks",
            user_message=(
                "선택한 계획의 과제를 불러오지 못해 직접 질문만 "
                "사용할 수 있습니다."
            ),
        )

    try:
        learning_materials, review_materials = (
            get_reference_materials_snapshot(
                supabase,
                user_id,
                selected_plan_id,
                st.session_state,
                loader=lambda: (
                    get_learning_materials_by_plan(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=selected_plan_id,
                    ),
                    get_review_materials_by_plan(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=selected_plan_id,
                    ),
                ),
            )
        )
    except Exception as error:
        learning_materials = []
        review_materials = []
        render_unexpected_warning(
            error,
            operation="tutor.load_materials",
            user_message=(
                "선택한 계획의 참고자료를 불러오지 못해 참고자료 없이 "
                "튜터를 시작할 수 있습니다."
            ),
        )

    task_by_id = {str(task["id"]): task for task in tasks}
    material_by_key = build_reference_material_options(
        learning_materials,
        review_materials,
    )
    applied_context_task: dict | None = None
    if context_plan_id is not None:
        if (
            context_plan_id == selected_plan_id
            and context_task_id in task_by_id
        ):
            st.session_state[SETUP_TASK_KEY] = context_task_id
            applied_context_task = task_by_id[context_task_id]
        else:
            st.warning(
                "이전 화면에서 가져온 과제를 찾을 수 없습니다. "
                "연결할 과제를 다시 선택해주세요."
            )
        clear_learning_context(st.session_state)

    task_options: list[str | None] = [None, *task_by_id]
    material_options: list[str | None] = [None, *material_by_key]
    task_selection_reset = _ensure_valid_widget_value(
        SETUP_TASK_KEY,
        task_options,
    )
    material_selection_reset = _ensure_valid_widget_value(
        SETUP_MATERIAL_KEY,
        material_options,
    )
    if task_selection_reset:
        st.info(
            "계획이 바뀌었거나 선택한 과제가 없어 과제 선택을 초기화했습니다."
        )
    if material_selection_reset:
        st.info(
            "계획이 바뀌었거나 선택한 자료가 없어 참고자료 선택을 "
            "초기화했습니다."
        )

    if applied_context_task is not None:
        st.success(
            f"{_get_context_source_label(context_source)}에서 선택한 "
            f"‘{applied_context_task['title']}’ 과제를 연결했습니다.",
            icon=":material/link:",
        )

    if not tasks:
        st.caption("선택한 계획에 과제가 없어 직접 질문으로 진행합니다.")
    if not material_by_key:
        st.caption("선택할 저장 자료가 없어 참고자료 없이 진행합니다.")

    with st.form("tutor_setup_form"):
        setup_columns = st.columns(2, gap="large")
        with setup_columns[0]:
            st.subheader("연결 정보")
            selected_task_id = st.selectbox(
                "연결할 과제 (선택)",
                options=task_options,
                format_func=lambda task_id: (
                    "선택하지 않음 · 직접 질문"
                    if task_id is None
                    else (
                        f"{task_by_id[task_id]['scheduled_date']} · "
                        f"{task_by_id[task_id]['title']}"
                    )
                ),
                key=SETUP_TASK_KEY,
            )
            selected_material_key = st.selectbox(
                "참고자료 (선택)",
                options=material_options,
                format_func=lambda material_key: (
                    "선택하지 않음"
                    if material_key is None
                    else material_by_key[material_key]["label"]
                ),
                key=SETUP_MATERIAL_KEY,
            )
            st.caption(
                "과제와 참고자료를 고르지 않아도 직접 질문할 수 있습니다."
            )
        with setup_columns[1]:
            st.subheader("질문과 현재 풀이")
            question = st.text_area(
                "질문 또는 문제",
                height=180,
                placeholder="풀이 과정을 도움받고 싶은 문제를 입력하세요.",
                key=SETUP_QUESTION_KEY,
            )
            uploaded_images = st.file_uploader(
                f"문제 스크린샷 (선택, 최대 {MAX_IMAGE_COUNT}장)",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True,
                max_upload_size=(
                    MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)
                ),
                help=(
                    f"파일당 최대 {MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)}MB, "
                    f"전체 {MAX_TOTAL_IMAGE_UPLOAD_BYTES // (1024 * 1024)}MB, "
                    f"최대 {MAX_IMAGE_COUNT}장. 첨부 순서대로 분석하며 "
                    "현재 튜터 세션에만 사용합니다."
                ),
                key=SETUP_IMAGES_KEY,
            )
            user_attempt = st.text_area(
                "현재 풀이 또는 생각 (선택)",
                height=150,
                placeholder="지금까지 시도한 방법이나 막힌 지점을 적어주세요.",
                key=SETUP_ATTEMPT_KEY,
            )
            st.caption(
                f"질문과 풀이는 각각 최대 {MAX_TUTOR_QUESTION_CHARS:,}자, "
                f"{MAX_TUTOR_ATTEMPT_CHARS:,}자까지 사용할 수 있습니다. "
                "텍스트 질문이나 문제 스크린샷 중 하나는 필요합니다."
            )
        start_submitted = st.form_submit_button(
            "AI 튜터 시작하기",
            key="tutor_start_submit",
            type="primary",
            icon=":material/explore:",
            width="stretch",
            disabled=bool(
                st.session_state.get(REQUEST_IN_PROGRESS_KEY, False)
            ),
        )

    if not start_submitted:
        return

    started = False
    try:
        if selected_plan_id not in plan_by_id:
            raise TutorInputValidationError(
                "본인의 저장된 학습계획을 다시 선택해주세요."
            )
        if selected_task_id is not None and selected_task_id not in task_by_id:
            raise TutorInputValidationError(
                "선택한 과제를 찾을 수 없습니다. 다시 선택해주세요."
            )
        if (
            selected_material_key is not None
            and selected_material_key not in material_by_key
        ):
            raise TutorInputValidationError(
                "선택한 참고자료를 찾을 수 없습니다. 다시 선택해주세요."
            )

        problem_images = (
            prepare_images_for_ai(
                [
                    (
                        uploaded_image.getvalue(),
                        uploaded_image.name,
                        uploaded_image.type,
                    )
                    for uploaded_image in uploaded_images
                ]
            )
            if uploaded_images
            else ()
        )
        cleaned_question = validate_tutor_problem_input(
            question,
            problem_images,
        )
        cleaned_attempt = validate_tutor_attempt(user_attempt)
        selected_plan = plan_by_id[selected_plan_id]
        selected_task = (
            task_by_id[selected_task_id]
            if selected_task_id is not None
            else None
        )
        selected_material = (
            material_by_key[selected_material_key]
            if selected_material_key is not None
            else None
        )

        st.session_state[REQUEST_IN_PROGRESS_KEY] = True
        with operation_status(
            "문제와 학습 문맥을 분석하고 있습니다...",
            "세 단계 힌트 준비를 완료했습니다",
            "AI 튜터 준비 중 오류가 발생했습니다",
        ) as status:
            status.write("선택한 과제·참고자료와 현재 풀이를 확인합니다.")
            generation_result = generate_tutor_guidance(
                course_name=selected_plan["course_name"],
                goal=selected_plan["goal"],
                current_level=selected_plan["current_level"],
                task_title=(
                    selected_task["title"] if selected_task else None
                ),
                task_description=(
                    selected_task["description"] if selected_task else None
                ),
                reference_title=(
                    selected_material["title"]
                    if selected_material
                    else None
                ),
                reference_context=(
                    selected_material["content"]
                    if selected_material
                    else None
                ),
                question=cleaned_question,
                user_attempt=cleaned_attempt,
                problem_images=problem_images,
            )
            status.write("힌트 1~3과 최종 풀이 구조를 검증했습니다.")

        st.session_state.update(
            create_tutor_session_state(
                session_id=str(uuid4()),
                user_id=user_id,
                plan_id=selected_plan_id,
                task_id=selected_task_id,
                material_key=selected_material_key,
                course_name=selected_plan["course_name"],
                task_title=(
                    selected_task["title"] if selected_task else None
                ),
                reference_title=(
                    selected_material["title"]
                    if selected_material
                    else None
                ),
                reference_context=generation_result.reference_context,
                reference_was_limited=(
                    generation_result.reference_was_limited
                ),
                question=generation_result.resolved_question,
                original_attempt=cleaned_attempt,
                guidance=generation_result.guidance,
                problem_images=[
                    problem_image.to_session_payload()
                    for problem_image in problem_images
                ],
            )
        )
        started = True
    except (TutorInputValidationError, ImageInputValidationError) as error:
        st.warning(str(error))
    except Exception as error:
        render_unexpected_error(
            error,
            operation="tutor.start",
            user_message=(
                "AI 튜터를 시작하지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
    finally:
        st.session_state[REQUEST_IN_PROGRESS_KEY] = False

    if started:
        st.rerun()


def render_tutor(supabase, user) -> None:
    """단계별 힌트 AI 튜터 화면을 표시합니다."""

    user_id = str(user.id)
    render_page_header(
        "단계별 힌트 AI 튜터",
        "정답을 바로 보여주지 않고 세 단계 힌트로 풀이 방향을 잡아드립니다.",
    )

    active_user_id = st.session_state.get(ACTIVE_USER_ID_KEY)
    if active_user_id is not None and active_user_id != user_id:
        clear_tutor_state(st.session_state)

    if st.session_state.get(ACTIVE_SESSION_ID_KEY):
        _render_active_tutor_session(user_id)
    else:
        st.session_state.setdefault(REQUEST_IN_PROGRESS_KEY, False)
        st.session_state.setdefault(FEEDBACK_IN_PROGRESS_KEY, False)
        _render_tutor_setup(supabase, user_id)
