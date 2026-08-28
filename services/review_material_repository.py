from supabase import Client

from models.review_material import ReviewMaterialDraft
from services.source_material_service import sanitize_database_text


def _prepare_database_text(value: str, field_name: str) -> str:
    """DB 저장 직전에 NUL을 제거하고 비어 버린 문자열을 거부합니다."""

    sanitized_value = sanitize_database_text(value)
    if not sanitized_value.strip():
        raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
    return sanitized_value


def get_learning_materials_by_plan(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> list[dict]:
    """본인 계획에 저장된 원본 학습자료 목록을 불러옵니다."""

    response = (
        supabase.table("learning_materials")
        .select(
            "id, user_id, plan_id, title, material_type, "
            "content_text, created_at"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def get_review_materials_by_plan(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> list[dict]:
    """본인 계획에 저장된 AI 학습·복습자료 목록을 불러옵니다."""

    response = (
        supabase.table("review_materials")
        .select(
            "id, user_id, plan_id, task_id, source_material_id, "
            "title, content_markdown, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data or []


def _build_source_review_material_bundles(
    learning_materials: list[dict],
    review_materials: list[dict],
    user_id: str,
    plan_id: str,
) -> list[dict]:
    """같은 사용자·계획에 속한 원본과 복습자료만 안전하게 연결합니다."""

    source_by_id = {
        str(source_material["id"]): source_material
        for source_material in learning_materials
        if source_material.get("id")
        and str(source_material.get("user_id")) == user_id
        and str(source_material.get("plan_id")) == plan_id
    }

    bundles = []
    for review_material in review_materials:
        source_material_id = review_material.get("source_material_id")
        if (
            not source_material_id
            or str(review_material.get("user_id")) != user_id
            or str(review_material.get("plan_id")) != plan_id
        ):
            continue

        source_material = source_by_id.get(str(source_material_id))
        if source_material is None:
            continue

        bundles.append(
            {
                "source_material": source_material,
                "review_material": review_material,
            }
        )

    return bundles


def get_source_review_material_bundles_by_plan(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> list[dict]:
    """본인 계획의 원본 기반 AI 복습자료 보관함을 불러옵니다."""

    source_response = (
        supabase.table("learning_materials")
        .select(
            "id, user_id, plan_id, title, material_type, created_at"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .order("created_at", desc=True)
        .execute()
    )
    learning_materials = source_response.data or []
    source_material_ids = [
        str(source_material["id"])
        for source_material in learning_materials
        if source_material.get("id")
    ]
    if not source_material_ids:
        return []

    review_response = (
        supabase.table("review_materials")
        .select(
            "id, user_id, plan_id, task_id, source_material_id, "
            "title, content_markdown, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .in_("source_material_id", source_material_ids)
        .order("updated_at", desc=True)
        .execute()
    )
    return _build_source_review_material_bundles(
        learning_materials=learning_materials,
        review_materials=review_response.data or [],
        user_id=user_id,
        plan_id=plan_id,
    )


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
        "title": _prepare_database_text(material.title, "학습자료 제목"),
        "content_markdown": _prepare_database_text(
            material.content_markdown,
            "학습자료 내용",
        ),
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
                "title": _prepare_database_text(title, "원본 제목"),
                "material_type": material_type,
                "content_text": _prepare_database_text(
                    content_text,
                    "원본 내용",
                ),
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
                "title": _prepare_database_text(
                    material.title,
                    "복습자료 제목",
                ),
                "content_markdown": _prepare_database_text(
                    material.content_markdown,
                    "복습자료 내용",
                ),
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


def delete_source_review_material(
    supabase: Client,
    user_id: str,
    plan_id: str,
    review_material_id: str,
    source_material_id: str,
) -> dict:
    """본인 원본 기반 복습자료와 미사용 원본을 원자적으로 삭제합니다."""

    required_ids = {
        "사용자 ID": user_id,
        "학습계획 ID": plan_id,
        "복습자료 ID": review_material_id,
        "원본 자료 ID": source_material_id,
    }
    for field_name, field_value in required_ids.items():
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(f"{field_name}가 필요합니다.")

    response = (
        supabase.rpc(
            "delete_source_review_material",
            {
                "p_review_material_id": review_material_id,
                "p_source_material_id": source_material_id,
                "p_plan_id": plan_id,
            },
        )
        .execute()
    )
    result = response.data
    if not isinstance(result, dict):
        raise RuntimeError("복습자료 삭제 결과가 비어 있습니다.")

    required_fields = {
        "review_material_id",
        "source_material_id",
        "source_deleted",
    }
    if not required_fields.issubset(result):
        raise RuntimeError("복습자료 삭제 응답 형식이 올바르지 않습니다.")
    if (
        str(result["review_material_id"]) != review_material_id
        or str(result["source_material_id"]) != source_material_id
        or not isinstance(result["source_deleted"], bool)
    ):
        raise RuntimeError("복습자료 삭제 응답 값이 올바르지 않습니다.")

    return result


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
