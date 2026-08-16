import hashlib

import streamlit as st

from services.review_material_repository import (
    save_source_review_material_bundle,
)
from services.review_material_service import (
    generate_source_review_material,
)
from services.source_material_service import (
    MAX_PDF_UPLOAD_BYTES,
    SourceMaterialValidationError,
    extract_pdf_text,
    validate_source_text,
    validate_source_title,
)
from services.study_plan_repository import get_user_study_plans


RESULT_STATE_KEY = "source_review_material_result"
FINGERPRINT_STATE_KEY = "source_review_material_fingerprint"
RUNNING_STATE_KEY = "source_review_material_running"
SOURCE_TYPE_KEY = "source_review_material_source_type"
PLAN_KEY = "source_review_material_plan_id"
TITLE_KEY = "source_review_material_title"
TEXT_KEY = "source_review_material_text"
PDF_KEY = "source_review_material_pdf"
SOURCE_REVIEW_SESSION_KEYS = (
    RESULT_STATE_KEY,
    FINGERPRINT_STATE_KEY,
    RUNNING_STATE_KEY,
    SOURCE_TYPE_KEY,
    PLAN_KEY,
    TITLE_KEY,
    TEXT_KEY,
    PDF_KEY,
)


def _build_request_fingerprint(
    user_id: str,
    plan_id: str,
    source_title: str,
    material_type: str,
    source_text: str,
) -> str:
    """같은 Streamlit 제출 요청을 식별할 세션용 지문을 만듭니다."""

    request_content = "\x1f".join(
        [
            user_id,
            plan_id,
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


def render_source_review_material(supabase, user) -> None:
    """텍스트 또는 PDF 원본 기반 AI 복습자료 생성 화면을 표시합니다."""

    user_id = str(user.id)
    st.header("AI 복습 자료 만들기")
    st.write(
        "직접 붙여넣은 글이나 텍스트가 포함된 PDF를 바탕으로 "
        "한국어 복습 자료를 만듭니다."
    )
    st.caption(
        "PDF 원본 파일은 저장하지 않으며 추출한 텍스트만 저장합니다. "
        "스캔본과 이미지 전용 PDF는 현재 지원하지 않습니다."
    )

    _clear_other_user_result(user_id)
    st.session_state.setdefault(RUNNING_STATE_KEY, False)

    try:
        study_plans = get_user_study_plans(
            supabase=supabase,
            user_id=user_id,
        )
    except Exception as error:
        st.error(f"저장된 학습계획을 불러오지 못했습니다: {error}")
        return

    if not study_plans:
        st.info("먼저 학습계획을 생성하고 저장해주세요.")
        return

    plan_by_id = {
        str(plan["id"]): plan
        for plan in study_plans
    }
    plan_ids = list(plan_by_id)

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
        selected_plan_id = st.selectbox(
            "학습계획",
            options=plan_ids,
            format_func=lambda plan_id: (
                f"{plan_by_id[plan_id]['title']} · "
                f"{plan_by_id[plan_id]['course_name']}"
            ),
            key=PLAN_KEY,
        )
        source_title = st.text_input(
            "원본 제목",
            max_chars=200,
            placeholder="예: 데이터베이스 정규화 강의 노트",
            key=TITLE_KEY,
        )

        pasted_text = None
        uploaded_pdf = None
        if source_type == "text":
            pasted_text = st.text_area(
                "원본 텍스트",
                height=280,
                placeholder="복습 자료로 만들 내용을 붙여넣으세요.",
                key=TEXT_KEY,
            )
        else:
            uploaded_pdf = st.file_uploader(
                "PDF 파일",
                type=["pdf"],
                accept_multiple_files=False,
                max_upload_size=MAX_PDF_UPLOAD_BYTES // (1024 * 1024),
                help="최대 10MB의 텍스트 기반 PDF만 지원합니다.",
                key=PDF_KEY,
            )

        submitted = st.form_submit_button(
            "AI 복습 자료 생성하기",
            type="primary",
            icon=":material/auto_awesome:",
            disabled=st.session_state[RUNNING_STATE_KEY],
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
                if source_type == "text":
                    source_text = validate_source_text(pasted_text or "")
                else:
                    if uploaded_pdf is None:
                        raise SourceMaterialValidationError(
                            "PDF 파일을 선택해주세요."
                        )
                    source_text = extract_pdf_text(
                        pdf_bytes=uploaded_pdf.getvalue(),
                        filename=uploaded_pdf.name,
                    )

                request_fingerprint = _build_request_fingerprint(
                    user_id=user_id,
                    plan_id=selected_plan_id,
                    source_title=cleaned_title,
                    material_type=source_type,
                    source_text=source_text,
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
                    st.session_state[RUNNING_STATE_KEY] = True

                    with st.spinner(
                        "원본을 분석하고 AI 복습 자료를 생성·저장하고 있습니다..."
                    ):
                        generated_material = generate_source_review_material(
                            source_title=cleaned_title,
                            course_name=selected_plan["course_name"],
                            goal=selected_plan["goal"],
                            current_level=selected_plan["current_level"],
                            source_text=source_text,
                        )
                        saved_bundle = save_source_review_material_bundle(
                            supabase=supabase,
                            user_id=user_id,
                            plan_id=selected_plan_id,
                            source_title=cleaned_title,
                            material_type=source_type,
                            source_text=source_text,
                            material=generated_material,
                        )

                    st.session_state[RESULT_STATE_KEY] = {
                        "user_id": user_id,
                        "plan_id": selected_plan_id,
                        "source_title": cleaned_title,
                        "material_type": source_type,
                        "review_material": saved_bundle[
                            "review_material"
                        ],
                    }
                    st.session_state[
                        FINGERPRINT_STATE_KEY
                    ] = request_fingerprint
                    st.success("AI 복습 자료를 생성하고 저장했습니다.")

            except SourceMaterialValidationError as error:
                st.warning(str(error))
            except Exception as error:
                st.error(f"AI 복습 자료 생성 또는 저장에 실패했습니다: {error}")
            finally:
                st.session_state[RUNNING_STATE_KEY] = False

    result = st.session_state.get(RESULT_STATE_KEY)
    if (
        result is None
        or result.get("user_id") != user_id
        or result.get("plan_id") != selected_plan_id
    ):
        return

    review_material = result["review_material"]
    st.divider()
    st.subheader("생성된 복습 자료")
    st.caption(
        f"원본: {result['source_title']} · "
        f"유형: {'PDF' if result['material_type'] == 'pdf' else '텍스트'}"
    )
    st.markdown(f"### {review_material['title']}")
    st.markdown(review_material["content_markdown"])
