def build_reference_material_options(
    learning_materials: list[dict],
    review_materials: list[dict],
) -> dict[str, dict]:
    """저장된 원본과 AI 자료를 공통 참고자료 선택 항목으로 변환합니다."""

    material_options: dict[str, dict] = {}

    for material in learning_materials:
        material_id = material.get("id")
        title = material.get("title")
        if material_id is None or not isinstance(title, str):
            continue

        material_key = f"learning:{material_id}"
        material_type = material.get("material_type", "text")
        material_options[material_key] = {
            "id": str(material_id),
            "kind": "learning",
            "title": title,
            "label": (
                f"원본 자료 · {title} "
                f"({'PDF' if material_type == 'pdf' else '텍스트'})"
            ),
            "content": material.get("content_text"),
            "learning_objective_id": material.get("learning_objective_id"),
        }

    for material in review_materials:
        material_id = material.get("id")
        title = material.get("title")
        if material_id is None or not isinstance(title, str):
            continue

        material_key = f"review:{material_id}"
        material_options[material_key] = {
            "id": str(material_id),
            "kind": "review",
            "title": title,
            "label": f"AI 학습·복습 자료 · {title}",
            "content": material.get("content_markdown"),
            "learning_objective_id": material.get("learning_objective_id"),
            "objective_snapshot": material.get("objective_snapshot"),
            "objective_contract_hash": material.get(
                "objective_contract_hash"
            ),
        }

    return material_options
