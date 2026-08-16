from supabase import Client

from models.review_material import ReviewMaterialDraft


def get_review_material_by_task(
    supabase: Client,
    user_id: str,
    task_id: str,
) -> dict | None:
    """특정 과제에 저장된 AI 학습자료를 불러옵니다."""

    response = (
        supabase.table("review_materials")
        .select(
            "id, user_id, plan_id, task_id, "
            "source_material_id, title, "
            "content_markdown, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("task_id", task_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def save_review_material(
    supabase: Client,
    user_id: str,
    plan_id: str,
    task_id: str,
    material: ReviewMaterialDraft,
) -> dict:
    """AI 학습자료를 과제당 하나씩 저장하거나 갱신합니다."""

    material_data = {
        "user_id": user_id,
        "plan_id": plan_id,
        "task_id": task_id,
        "title": material.title,
        "content_markdown": material.content_markdown,
    }

    response = (
        supabase.table("review_materials")
        .upsert(
            material_data,
            on_conflict="task_id",
        )
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "AI 학습자료 저장 결과가 비어 있습니다."
        )

    return response.data[0]


def create_learning_material(
    supabase: Client,
    user_id: str,
    plan_id: str,
    title: str,
    material_type: str,
    content_text: str,
) -> dict:
    """추출·검증된 사용자 원본 텍스트를 저장합니다."""

    response = (
        supabase.table("learning_materials")
        .insert(
            {
                "user_id": user_id,
                "plan_id": plan_id,
                "title": title,
                "material_type": material_type,
                "content_text": content_text,
                "storage_path": None,
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("원본 학습자료 저장 결과가 비어 있습니다.")
    return response.data[0]


def create_source_review_material(
    supabase: Client,
    user_id: str,
    plan_id: str,
    source_material_id: str,
    material: ReviewMaterialDraft,
) -> dict:
    """원본 학습자료와 연결된 AI 복습자료를 저장합니다."""

    response = (
        supabase.table("review_materials")
        .insert(
            {
                "user_id": user_id,
                "plan_id": plan_id,
                "source_material_id": source_material_id,
                "title": material.title,
                "content_markdown": material.content_markdown,
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("AI 복습자료 저장 결과가 비어 있습니다.")
    return response.data[0]


def delete_learning_material(
    supabase: Client,
    user_id: str,
    plan_id: str,
    material_id: str,
) -> None:
    """이번 요청에서 새로 만든 미사용 원본 행만 정리합니다."""

    response = (
        supabase.table("learning_materials")
        .delete()
        .eq("id", material_id)
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError("미사용 원본 학습자료를 정리하지 못했습니다.")


def save_source_review_material_bundle(
    supabase: Client,
    user_id: str,
    plan_id: str,
    source_title: str,
    material_type: str,
    source_text: str,
    material: ReviewMaterialDraft,
) -> dict:
    """원본과 AI 결과를 순서대로 저장하고 부분 실패를 정리합니다."""

    if material_type not in {"text", "pdf"}:
        raise ValueError("원본 자료 유형은 text 또는 pdf여야 합니다.")

    source_material = create_learning_material(
        supabase=supabase,
        user_id=user_id,
        plan_id=plan_id,
        title=source_title,
        material_type=material_type,
        content_text=source_text,
    )

    try:
        review_material = create_source_review_material(
            supabase=supabase,
            user_id=user_id,
            plan_id=plan_id,
            source_material_id=source_material["id"],
            material=material,
        )
    except Exception as save_error:
        try:
            delete_learning_material(
                supabase=supabase,
                user_id=user_id,
                plan_id=plan_id,
                material_id=source_material["id"],
            )
        except Exception as cleanup_error:
            raise RuntimeError(
                "AI 복습자료 저장에 실패했고 새 원본 행도 자동으로 "
                "정리하지 못했습니다. 관리자 확인이 필요합니다."
            ) from cleanup_error

        raise RuntimeError(
            "AI 복습자료 저장에 실패해 새 원본 행을 정리했습니다. "
            f"원인: {save_error}"
        ) from save_error

    return {
        "source_material": source_material,
        "review_material": review_material,
    }
