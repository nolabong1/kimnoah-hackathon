import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from services.learner_context_service import load_learner_context
from services.learning_objective_repository import (
    get_learning_objectives_by_plan_ids,
)
from services.pdf_visual_extraction_service import (
    MAX_VISUAL_PDF_PAGES,
    extract_pdf_with_ai_vision,
)
from services.review_material_repository import (
    delete_source_review_material,
    get_source_review_material_bundles_by_plan,
    save_source_review_material_bundle,
)
from services.review_material_service import (
    estimate_source_review_ai_calls,
    generate_source_review_material,
)
from services.source_material_service import (
    MAX_PDF_UPLOAD_BYTES,
    MAX_SOURCE_TEXT_CHARS,
    SourceMaterialValidationError,
    extract_pdf_document,
    inspect_pdf_upload,
    validate_source_text,
    validate_source_title,
)
from services.study_plan_repository import get_user_study_plans
from views.error_feedback import (
    render_unexpected_error,
    render_unexpected_warning,
)
from views.operation_feedback import operation_status
from views.ui_components import render_empty_state, render_page_header


RESULT_STATE_KEY = "source_review_material_result"
FINGERPRINT_STATE_KEY = "source_review_material_fingerprint"
RUNNING_STATE_KEY = "source_review_material_running"
SOURCE_TYPE_KEY = "source_review_material_source_type"
PLAN_KEY = "source_review_material_plan_id"
OBJECTIVE_KEY = "source_review_material_objective_id"
TITLE_KEY = "source_review_material_title"
TEXT_KEY = "source_review_material_text"
PDF_KEY = "source_review_material_pdf"
PDF_READING_MODE_KEY = "source_review_material_pdf_reading_mode"
VIEW_MODE_KEY = "source_review_material_view_mode"
ARCHIVE_PLAN_KEY = "source_review_material_archive_plan_id"
ARCHIVE_ITEM_KEY = "source_review_material_archive_item_id"
DELETED_ITEM_CLEANUP_KEY = "source_review_material_deleted_item_id"
DELETE_MESSAGE_KEY = "source_review_material_delete_message"
SOURCE_REVIEW_SESSION_KEYS = (
    RESULT_STATE_KEY,
    FINGERPRINT_STATE_KEY,
    RUNNING_STATE_KEY,
    SOURCE_TYPE_KEY,
    PLAN_KEY,
    OBJECTIVE_KEY,
    TITLE_KEY,
    TEXT_KEY,
    PDF_KEY,
    PDF_READING_MODE_KEY,
    VIEW_MODE_KEY,
    ARCHIVE_PLAN_KEY,
    ARCHIVE_ITEM_KEY,
    DELETED_ITEM_CLEANUP_KEY,
    DELETE_MESSAGE_KEY,
)

SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")


def _build_request_fingerprint(
    user_id: str,
    plan_id: str,
    learning_objective_id: str,
    source_title: str,
    material_type: str,
    source_text: str,
) -> str:
    """같은 Streamlit 제출 요청을 식별할 세션용 지문을 만듭니다."""

    request_content = "\x1f".join(
        [
            user_id,
            plan_id,
            learning_objective_id,
            source_title,
            material_type,
            source_text,
        ]
    )
    return hashlib.sha256(request_content.encode("utf-8")).hexdigest()


def _clear_other_user_result(user_id: str) -> None:
    """같은 브라우저 세션에 남은 다른 사용자의 미리보기를 제거합니다."""

    saved_result = st.session_state.get(RESULT_STATE_KEY)
    if saved_result and saved_result.get("user_id") != user_id:
        st.session_state.pop(RESULT_STATE_KEY, None)
        st.session_state.pop(FINGERPRINT_STATE_KEY, None)


def _apply_deleted_material_state() -> None:
    """삭제 다음 rerun에서 관련 위젯과 생성 결과 상태를 정리합니다."""

    deleted_item_id = st.session_state.pop(
        DELETED_ITEM_CLEANUP_KEY,
        None,
    )
    if deleted_item_id is None:
        return

    st.session_state.pop(ARCHIVE_ITEM_KEY, None)
    saved_result = st.session_state.get(RESULT_STATE_KEY)
    saved_review = (
        saved_result.get("review_material", {})
        if isinstance(saved_result, dict)
        else {}
    )
    if str(saved_review.get("id")) == str(deleted_item_id):
        st.session_state.pop(RESULT_STATE_KEY, None)
        st.session_state.pop(FINGERPRINT_STATE_KEY, None)


@st.dialog("복습자료 삭제")
def _show_delete_source_review_material_dialog(
    supabase,
    user_id: str,
    plan_id: str,
    bundle: dict,
) -> None:
    """선택한 원본 기반 복습자료의 영구 삭제를 확인합니다."""

    review_material = bundle["review_material"]
    source_material = bundle["source_material"]
    st.warning(
        "삭제한 복습자료는 복구할 수 없습니다.",
        icon=":material/warning:",
    )
    st.write(
        f"**{review_material.get('title', '제목 없는 복습자료')}**를 "
        "삭제할까요?"
    )
    st.caption(
        "생성된 AI 복습자료와 저장된 원본 추출 텍스트가 함께 "
        "삭제됩니다. 학습계획, 과제, 퀴즈와 EXP에는 영향을 주지 않습니다."
    )

    with st.container(
        horizontal=True,
        horizontal_alignment="right",
    ):
        if st.button(
            "취소",
            key=f"cancel_delete_source_review_{review_material['id']}",
        ):
            st.rerun()

        if st.button(
            "삭제하기",
            key=f"confirm_delete_source_review_{review_material['id']}",
            type="primary",
            icon=":material/delete:",
        ):
            try:
                with st.spinner("복습자료를 삭제하고 있습니다..."):
                    delete_source_review_material(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                        review_material_id=str(review_material["id"]),
                        source_material_id=str(source_material["id"]),
                    )

                st.session_state[DELETED_ITEM_CLEANUP_KEY] = str(
                    review_material["id"]
                )
                st.session_state[DELETE_MESSAGE_KEY] = (
                    f"'{review_material.get('title', '복습자료')}'를 "
                    "삭제했습니다."
                )
                st.rerun()
            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="source_review.delete",
                    user_message=(
                        "복습자료를 삭제하지 못했습니다. 잠시 후 다시 "
                        "시도해주세요."
                    ),
                )


def _format_saved_at(value: object) -> str:
    """Supabase 저장 시각을 서울 기준의 짧은 표시로 변환합니다."""

    if not value:
        return "저장 시각 정보 없음"
    try:
        parsed_value = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed_value.tzinfo is None:
            parsed_value = parsed_value.replace(tzinfo=SEOUL_TIMEZONE)
        return parsed_value.astimezone(SEOUL_TIMEZONE).strftime(
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return str(value)


def _render_saved_source_review_materials(
    supabase,
    user_id: str,
    plan_by_id: dict[str, dict],
) -> None:
    """계획별로 저장된 원본 기반 AI 복습자료를 표시합니다."""

    plan_ids = list(plan_by_id)
    if st.session_state.get(ARCHIVE_PLAN_KEY) not in plan_ids:
        st.session_state[ARCHIVE_PLAN_KEY] = plan_ids[0]

    selected_plan_id = st.selectbox(
        "확인할 학습계획",
        options=plan_ids,
        format_func=lambda plan_id: (
            f"{plan_by_id[plan_id]['title']} · "
            f"{plan_by_id[plan_id]['course_name']}"
        ),
        key=ARCHIVE_PLAN_KEY,
    )

    try:
        saved_bundles = get_source_review_material_bundles_by_plan(
            supabase=supabase,
            user_id=user_id,
            plan_id=selected_plan_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="source_review.load_saved_materials",
            user_message=(
                "저장된 복습자료를 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not saved_bundles:
        render_empty_state(
            "저장된 복습자료가 없습니다",
            "새 자료 만들기에서 텍스트나 PDF로 복습자료를 생성해주세요.",
            icon=":material/library_books:",
        )
        return

    bundle_by_id = {
        str(bundle["review_material"]["id"]): bundle
        for bundle in saved_bundles
    }
    bundle_ids = list(bundle_by_id)
    if st.session_state.get(ARCHIVE_ITEM_KEY) not in bundle_ids:
        st.session_state[ARCHIVE_ITEM_KEY] = bundle_ids[0]

    selector_column, detail_column = st.columns(
        [0.72, 1.28],
        gap="large",
        vertical_alignment="top",
    )
    with selector_column:
        with st.container(border=True):
            st.subheader("저장된 자료")
            selected_bundle_id = st.selectbox(
                "열어볼 복습자료",
                options=bundle_ids,
                format_func=lambda bundle_id: (
                    bundle_by_id[bundle_id]["review_material"].get(
                        "title", "제목 없는 복습자료"
                    )
                ),
                key=ARCHIVE_ITEM_KEY,
            )
            selected_bundle = bundle_by_id[selected_bundle_id]
            source_material = selected_bundle["source_material"]
            st.caption(
                "원본 · "
                f"{source_material.get('title', '제목 없음')} · "
                f"{'PDF' if source_material.get('material_type') == 'pdf' else '텍스트'}"
            )
            st.caption(
                "저장 · "
                f"{_format_saved_at(selected_bundle['review_material'].get('created_at'))}"
            )
            objective_snapshot = selected_bundle["review_material"].get(
                "objective_snapshot"
            )
            if isinstance(objective_snapshot, dict):
                st.caption(
                    "연결 목표 · "
                    f"{objective_snapshot.get('title', '제목 없음')}"
                )

    with detail_column:
        selected_bundle = bundle_by_id[selected_bundle_id]
        source_material = selected_bundle["source_material"]
        review_material = selected_bundle["review_material"]
        with st.container(border=True):
            st.caption(
                f"{plan_by_id[selected_plan_id]['course_name']} · "
                f"원본 {source_material.get('title', '제목 없음')}"
            )
            st.markdown(
                f"## {review_material.get('title', '제목 없는 복습자료')}"
            )
            st.markdown(review_material.get("content_markdown", ""))
            with st.container(
                horizontal=True,
                horizontal_alignment="right",
            ):
                if st.button(
                    "복습자료 삭제",
                    key=f"delete_source_review_{selected_bundle_id}",
                    icon=":material/delete:",
                ):
                    _show_delete_source_review_material_dialog(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=selected_plan_id,
                        bundle=selected_bundle,
                    )


def render_source_review_material(supabase, user) -> None:
    """텍스트 또는 PDF 원본 기반 AI 복습자료 생성 화면을 표시합니다."""

    user_id = str(user.id)
    render_page_header(
        "AI 복습 자료 만들기",
        "붙여넣은 글이나 텍스트형 PDF를 학습하기 좋은 한국어 자료로 정리합니다.",
    )
    st.caption(
        "PDF 원본 파일은 저장하지 않으며 추출한 텍스트만 저장합니다. "
        "페이지 경계와 읽기 순서를 보존해 분석하며, 스캔본과 이미지 전용 "
        f"PDF는 현재 지원하지 않습니다. 원본은 최대 "
        f"{MAX_SOURCE_TEXT_CHARS:,}자까지 처리합니다."
    )

    _clear_other_user_result(user_id)
    _apply_deleted_material_state()
    st.session_state.setdefault(RUNNING_STATE_KEY, False)

    delete_message = st.session_state.pop(DELETE_MESSAGE_KEY, None)
    if delete_message:
        st.success(delete_message)

    try:
        study_plans = get_user_study_plans(
            supabase=supabase,
            user_id=user_id,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="source_review.load_plans",
            user_message=(
                "저장된 학습계획을 불러오지 못했습니다. 잠시 후 다시 "
                "시도해주세요."
            ),
        )
        return

    if not study_plans:
        render_empty_state(
            "저장된 계획이 없습니다",
            "복습 자료를 연결할 학습계획을 먼저 만들어주세요.",
            icon=":material/article_shortcut:",
        )
        return

    plan_by_id = {
        str(plan["id"]): plan
        for plan in study_plans
    }
    plan_ids = list(plan_by_id)

    view_mode = st.segmented_control(
        "복습자료 화면",
        options=["create", "saved"],
        default="create",
        format_func=lambda value: (
            "새 자료 만들기" if value == "create" else "저장된 자료"
        ),
        key=VIEW_MODE_KEY,
        required=True,
        persist_state="page",
    )
    if view_mode == "saved":
        _render_saved_source_review_materials(
            supabase=supabase,
            user_id=user_id,
            plan_by_id=plan_by_id,
        )
        return

    try:
        objectives_by_plan = get_learning_objectives_by_plan_ids(
            supabase=supabase,
            user_id=user_id,
            plan_ids=plan_ids,
        )
    except Exception as error:
        render_unexpected_error(
            error,
            operation="source_review.load_learning_objectives",
            user_message=(
                "학습계획의 세부 목표를 불러오지 못했습니다. 잠시 후 "
                "다시 시도해주세요."
            ),
        )
        return

    input_column, result_column = st.columns(
        [0.9, 1.1],
        gap="large",
        vertical_alignment="top",
    )

    with input_column:
        with st.container(border=True):
            st.subheader("원본 준비")
            selected_plan_id = st.selectbox(
                "학습계획",
                options=plan_ids,
                format_func=lambda plan_id: (
                    f"{plan_by_id[plan_id]['title']} · "
                    f"{plan_by_id[plan_id]['course_name']}"
                ),
                key=PLAN_KEY,
            )
            plan_objectives = objectives_by_plan.get(selected_plan_id, [])
            if not plan_objectives:
                st.warning(
                    "선택한 계획에 연결할 학습목표가 없습니다. "
                    "학습목표 DB migration 적용 상태를 확인해주세요."
                )
                return
            objective_by_id = {
                str(objective.id): objective
                for objective in plan_objectives
            }
            if st.session_state.get(OBJECTIVE_KEY) not in objective_by_id:
                st.session_state[OBJECTIVE_KEY] = next(iter(objective_by_id))
            source_type = st.segmented_control(
                "원본 유형",
                options=["text", "pdf"],
                default="text",
                format_func=lambda value: (
                    "텍스트 붙여넣기" if value == "text" else "PDF 업로드"
                ),
                key=SOURCE_TYPE_KEY,
                required=True,
                persist_state="page",
            )

            with st.form("source_review_material_form"):
                selected_objective_id = st.selectbox(
                    "연결할 세부 학습목표",
                    options=list(objective_by_id),
                    format_func=lambda objective_id: (
                        objective_by_id[objective_id].title
                    ),
                    key=OBJECTIVE_KEY,
                    help=(
                        "원본을 어떤 학습목표의 자료로 사용할지 선택합니다."
                    ),
                )
                source_title = st.text_input(
                    "원본 제목",
                    max_chars=200,
                    placeholder="예: 데이터베이스 정규화 강의 노트",
                    key=TITLE_KEY,
                )

                pasted_text = None
                uploaded_pdf = None
                pdf_reading_mode = "text"
                if source_type == "text":
                    pasted_text = st.text_area(
                        "원본 텍스트",
                        height=280,
                        placeholder="복습 자료로 만들 내용을 붙여넣으세요.",
                        key=TEXT_KEY,
                    )
                else:
                    pdf_reading_mode = st.selectbox(
                        "PDF 읽기 방식",
                        options=["text", "ai_visual"],
                        format_func=lambda value: (
                            "빠른 텍스트 추출"
                            if value == "text"
                            else "AI 정밀 읽기 · 스캔·도표·수식"
                        ),
                        help=(
                            "AI 정밀 읽기는 PDF를 OpenAI에 한 번 전송해 "
                            "페이지 이미지까지 분석하므로 비용과 시간이 더 "
                            "필요합니다. 원본 파일은 앱이나 Supabase에 "
                            "저장하지 않습니다."
                        ),
                        key=PDF_READING_MODE_KEY,
                    )
                    uploaded_pdf = st.file_uploader(
                        "PDF 파일",
                        type=["pdf"],
                        accept_multiple_files=False,
                        max_upload_size=(
                            MAX_PDF_UPLOAD_BYTES // (1024 * 1024)
                        ),
                        help=(
                            "최대 10MB. AI 정밀 읽기는 최대 "
                            f"{MAX_VISUAL_PDF_PAGES}페이지까지 지원합니다."
                        ),
                        key=PDF_KEY,
                    )

                submitted = st.form_submit_button(
                    "AI 복습 자료 생성하기",
                    type="primary",
                    icon=":material/auto_awesome:",
                    disabled=st.session_state[RUNNING_STATE_KEY],
                    width="stretch",
                )

    if submitted:
        if st.session_state[RUNNING_STATE_KEY]:
            st.warning("이미 복습 자료를 생성하고 있습니다.")
        else:
            try:
                if source_type not in {"text", "pdf"}:
                    raise SourceMaterialValidationError(
                        "올바른 원본 유형을 선택해주세요."
                    )
                if selected_plan_id not in plan_by_id:
                    raise SourceMaterialValidationError(
                        "본인의 저장된 학습계획을 선택해주세요."
                    )

                cleaned_title = validate_source_title(source_title)
                extraction_summary = None
                visual_pdf_bytes = None
                if source_type == "text":
                    source_text = validate_source_text(pasted_text or "")
                    fingerprint_source = source_text
                else:
                    if uploaded_pdf is None:
                        raise SourceMaterialValidationError(
                            "PDF 파일을 선택해주세요."
                        )
                    pdf_bytes = uploaded_pdf.getvalue()
                    if pdf_reading_mode == "text":
                        extraction_result = extract_pdf_document(
                            pdf_bytes=pdf_bytes,
                            filename=uploaded_pdf.name,
                        )
                        source_text = extraction_result.text
                        extraction_summary = (
                            extraction_result.to_summary()
                        )
                        fingerprint_source = source_text
                    elif pdf_reading_mode == "ai_visual":
                        inspect_pdf_upload(
                            pdf_bytes=pdf_bytes,
                            filename=uploaded_pdf.name,
                        )
                        visual_pdf_bytes = pdf_bytes
                        source_text = None
                        fingerprint_source = (
                            "ai_visual:"
                            + hashlib.sha256(pdf_bytes).hexdigest()
                        )
                    else:
                        raise SourceMaterialValidationError(
                            "올바른 PDF 읽기 방식을 선택해주세요."
                        )

                request_fingerprint = _build_request_fingerprint(
                    user_id=user_id,
                    plan_id=selected_plan_id,
                    learning_objective_id=selected_objective_id,
                    source_title=cleaned_title,
                    material_type=source_type,
                    source_text=fingerprint_source,
                )
                saved_result = st.session_state.get(RESULT_STATE_KEY)
                if (
                    request_fingerprint
                    == st.session_state.get(FINGERPRINT_STATE_KEY)
                    and saved_result is not None
                ):
                    st.info(
                        "같은 요청으로 이미 저장된 결과를 표시합니다. "
                        "내용을 변경하면 새 자료를 생성할 수 있습니다."
                    )
                else:
                    selected_plan = plan_by_id[selected_plan_id]
                    selected_objective = objective_by_id[
                        selected_objective_id
                    ]
                    st.session_state[RUNNING_STATE_KEY] = True

                    with operation_status(
                        "원본과 학습목표를 분석하고 있습니다...",
                        "AI 복습 자료 생성과 저장을 완료했습니다",
                        "AI 복습 자료 처리 중 오류가 발생했습니다",
                    ) as status:
                        visual_extraction_calls = 0
                        if visual_pdf_bytes is not None:
                            status.write(
                                "PDF의 텍스트·표·도표를 AI 정밀 읽기로 추출합니다."
                            )
                            st.info(
                                "선택한 PDF를 OpenAI에 전송해 텍스트와 "
                                "페이지 이미지를 정밀 분석합니다. 원본 파일은 "
                                "앱이나 Supabase에 저장하지 않습니다."
                            )
                            extraction_result = (
                                extract_pdf_with_ai_vision(
                                    pdf_bytes=visual_pdf_bytes,
                                    filename=uploaded_pdf.name,
                                )
                            )
                            source_text = extraction_result.text
                            extraction_summary = (
                                extraction_result.to_summary()
                            )
                            visual_extraction_calls = 1
                        if source_text is None:
                            raise RuntimeError(
                                "PDF에서 복습자료용 텍스트를 준비하지 못했습니다."
                            )
                        status.write("원본 텍스트와 선택한 학습목표를 확인했습니다.")

                        estimated_ai_calls = (
                            estimate_source_review_ai_calls(source_text)
                            + visual_extraction_calls
                        )
                        if estimated_ai_calls > 1:
                            st.info(
                                "정상 처리 기준 AI 요청은 "
                                f"{estimated_ai_calls}회이며 원문 근거 교정이 "
                                "필요하면 추가 요청이 발생할 수 있습니다."
                            )
                        learner_context = None
                        status.write("현재 숙련도와 학습계획 문맥을 준비합니다.")
                        try:
                            learner_context = load_learner_context(
                                supabase=supabase,
                                user_id=user_id,
                                course_name=selected_plan["course_name"],
                            )
                        except Exception as error:
                            render_unexpected_warning(
                                error,
                                operation=(
                                    "source_review.load_learner_context"
                                ),
                                user_message=(
                                    "최근 숙련도는 불러오지 못해 학습계획과 "
                                    "원본 내용만으로 복습자료를 생성합니다."
                                ),
                            )
                        status.write("원문 근거를 유지하며 AI 복습 자료를 생성합니다.")
                        generated_material = generate_source_review_material(
                            source_title=cleaned_title,
                            course_name=selected_plan["course_name"],
                            goal=selected_plan["goal"],
                            current_level=selected_plan["current_level"],
                            source_text=source_text,
                            learner_context=learner_context,
                            learning_objective=selected_objective,
                        )
                        status.write("생성 결과와 추출 원문을 연결해 저장합니다.")
                        saved_bundle = save_source_review_material_bundle(
                            supabase=supabase,
                            user_id=user_id,
                            plan_id=selected_plan_id,
                            source_title=cleaned_title,
                            material_type=source_type,
                            source_text=source_text,
                            material=generated_material,
                            learning_objective_id=selected_objective_id,
                        )

                    st.session_state[RESULT_STATE_KEY] = {
                        "user_id": user_id,
                        "plan_id": selected_plan_id,
                        "learning_objective_id": selected_objective_id,
                        "learning_objective_title": selected_objective.title,
                        "source_title": cleaned_title,
                        "material_type": source_type,
                        "pdf_reading_mode": (
                            pdf_reading_mode
                            if source_type == "pdf"
                            else None
                        ),
                        "estimated_ai_calls": estimated_ai_calls,
                        "extraction_summary": extraction_summary,
                        "review_material": saved_bundle[
                            "review_material"
                        ],
                    }
                    st.session_state[
                        FINGERPRINT_STATE_KEY
                    ] = request_fingerprint

            except SourceMaterialValidationError as error:
                st.warning(str(error))
            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="source_review.generate_and_save",
                    user_message=(
                        "AI 복습 자료 생성 또는 저장에 실패했습니다. "
                        "잠시 후 다시 시도해주세요."
                    ),
                )
            finally:
                st.session_state[RUNNING_STATE_KEY] = False

    result = st.session_state.get(RESULT_STATE_KEY)
    with result_column:
        if (
            result is None
            or result.get("user_id") != user_id
            or result.get("plan_id") != selected_plan_id
            or result.get("learning_objective_id")
            != selected_objective_id
        ):
            render_empty_state(
                "생성 결과가 여기에 표시됩니다",
                "왼쪽에서 원본을 입력하고 AI 복습 자료를 생성해주세요.",
                icon=":material/auto_stories:",
            )
            return

        review_material = result["review_material"]
        with st.container(border=True):
            st.caption(
                f"원본 · {result['source_title']} · "
                f"{'PDF' if result['material_type'] == 'pdf' else '텍스트'}"
            )
            st.caption(
                "연결 목표 · "
                f"{result.get('learning_objective_title', '제목 없음')}"
            )
            st.success(
                "복습자료의 핵심 내용과 회상 문제에 사용된 원문 근거를 "
                "확인했습니다."
            )
            if result.get("pdf_reading_mode") == "ai_visual":
                st.caption(
                    "AI 정밀 읽기 사용 · PDF 텍스트와 페이지 이미지 분석"
                )
            if result.get("estimated_ai_calls", 1) > 1:
                st.caption(
                    "긴 원본 분할 분석 · 정상 처리 기준 "
                    f"AI 요청 {result['estimated_ai_calls']}회"
                )
            extraction_summary = result.get("extraction_summary")
            if extraction_summary is not None:
                st.caption(
                    "PDF 추출 · "
                    f"전체 {extraction_summary['page_count']}페이지 중 "
                    f"{extraction_summary['extracted_page_count']}페이지 사용"
                )
                for warning in extraction_summary.get("warnings", ()):
                    st.info(warning)
            st.markdown(f"## {review_material['title']}")
            st.markdown(review_material["content_markdown"])
