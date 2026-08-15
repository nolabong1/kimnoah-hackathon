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