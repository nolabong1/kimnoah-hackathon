import streamlit as st

from services.learner_context_service import load_learner_context
from services.learning_objective_repository import (
    get_learning_objective_for_task,
)
from services.review_material_repository import (
    get_review_material_by_task,
    save_review_material,
)
from services.review_material_service import (
    generate_review_material,
)
from views.error_feedback import (
    render_unexpected_error,
    render_unexpected_warning,
)
from views.operation_feedback import operation_status
from views.reference_material_state import (
    invalidate_reference_material_snapshots,
)


def render_review_material_section(
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
    """과제의 AI 학습자료 생성·저장·조회 UI를 표시합니다."""

    if display_mode not in {"toggle", "open"}:
        raise ValueError("지원하지 않는 AI 학습자료 표시 방식입니다.")

    material_section_open = display_mode == "open"
    if display_mode == "toggle":
        material_section_open = st.toggle(
            "AI 학습자료 열기",
            key=(
                f"{widget_scope}_review_material_section_"
                f"{task['id']}"
            ),
        )

    if not material_section_open:
        return

    with st.container(border=True):
        try:
            material = get_review_material_by_task(
                supabase=supabase,
                user_id=user_id,
                task_id=task["id"],
            )

        except Exception as error:
            render_unexpected_error(
                error,
                operation="review_material.load_for_task",
                user_message=(
                    "저장된 AI 학습자료를 불러오지 못했습니다. 잠시 후 "
                    "다시 시도해주세요."
                ),
            )
            return

        is_regeneration = material is not None

        if material is None:
            st.info(
                "아직 저장된 AI 학습자료가 없습니다. "
                "과제 정보를 바탕으로 새 자료를 "
                "생성할 수 있습니다."
            )
        elif isinstance(material.get("objective_snapshot"), dict):
            st.caption(
                "연결 목표 · "
                f"{material['objective_snapshot'].get('title', '제목 없음')}"
            )

        generate_button_label = (
            "AI 학습자료 다시 생성하기"
            if is_regeneration
            else "AI 학습자료 생성하기"
        )

        if st.button(
            generate_button_label,
            key=(
                f"{widget_scope}_generate_review_material_"
                f"{task['id']}"
            ),
            type=(
                "secondary"
                if is_regeneration
                else "primary"
            ),
        ):
            try:
                with operation_status(
                    "과제 문맥을 확인하고 있습니다...",
                    "AI 학습자료 생성과 저장을 완료했습니다",
                    "AI 학습자료 처리 중 오류가 발생했습니다",
                ) as status:
                    learner_context = None
                    learning_objective = None
                    status.write("현재 숙련도와 연결된 학습목표를 확인합니다.")
                    try:
                        learner_context = load_learner_context(
                            supabase=supabase,
                            user_id=user_id,
                            course_name=course_name,
                        )
                    except Exception as error:
                        render_unexpected_warning(
                            error,
                            operation="review_material.load_learner_context",
                            user_message=(
                                "최근 숙련도는 불러오지 못해 현재 계획과 "
                                "과제 정보만으로 자료를 생성합니다."
                            ),
                        )
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
                    material_draft = (
                        generate_review_material(
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
                            learner_context=learner_context,
                            learning_objective=learning_objective,
                        )
                    )

                    status.write("생성 결과를 검증하고 과제에 저장합니다.")
                    material = save_review_material(
                        supabase=supabase,
                        user_id=user_id,
                        plan_id=plan_id,
                        task_id=task["id"],
                        material=material_draft,
                    )
                    invalidate_reference_material_snapshots(
                        st.session_state,
                        str(plan_id),
                    )

            except Exception as error:
                render_unexpected_error(
                    error,
                    operation="review_material.generate_and_save",
                    user_message=(
                        "AI 학습자료 생성 또는 저장에 실패했습니다. 잠시 "
                        "후 다시 시도해주세요."
                    ),
                )

        if material is None:
            return

        st.markdown(f"### {material['title']}")
        st.markdown(material["content_markdown"])
