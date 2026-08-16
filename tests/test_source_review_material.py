import io
import unittest
from copy import deepcopy
from unittest.mock import patch

from pypdf import PdfWriter

from models.review_material import (
    ReviewMaterialDraft,
    SourceReviewMaterialDraft,
)
from services.review_material_repository import (
    save_source_review_material_bundle,
)
from services.review_material_service import (
    convert_source_review_to_markdown,
    generate_source_review_material,
)
from services.source_material_service import (
    MAX_SOURCE_TEXT_CHARS,
    SourceMaterialValidationError,
    extract_pdf_text,
    normalize_source_text,
    validate_source_text,
    validate_source_title,
)


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_ID = "33333333-3333-4333-8333-333333333333"


class FakeResponse:
    def __init__(self, data):
        self.data = deepcopy(data)


class FakeTableRequest:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = {}

    def insert(self, payload):
        self.operation = "insert"
        self.payload = deepcopy(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def execute(self):
        if self.table_name == "learning_materials":
            if self.operation == "insert":
                saved_row = {"id": SOURCE_ID, **self.payload}
                self.client.learning_materials.append(saved_row)
                return FakeResponse([saved_row])

            deleted_rows = [
                row
                for row in self.client.learning_materials
                if all(
                    row.get(field) == value
                    for field, value in self.filters.items()
                )
            ]
            self.client.learning_materials = [
                row
                for row in self.client.learning_materials
                if row not in deleted_rows
            ]
            return FakeResponse(deleted_rows)

        if self.client.fail_review_insert:
            raise RuntimeError("review insert failed")
        return FakeResponse([{"id": "review-id", **self.payload}])


class FakeSupabase:
    def __init__(self, fail_review_insert=False):
        self.fail_review_insert = fail_review_insert
        self.learning_materials = []

    def table(self, table_name):
        return FakeTableRequest(self, table_name)


def build_text_pdf_bytes(text: str) -> bytes:
    """외부 파일 없이 테스트용 단일 페이지 텍스트 PDF를 만듭니다."""

    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


class SourceMaterialValidationTests(unittest.TestCase):
    def test_title_is_stripped_and_validated(self):
        self.assertEqual(validate_source_title("  강의 노트  "), "강의 노트")
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_title("   ")
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_title("가" * 201)

    def test_text_normalization_preserves_paragraphs(self):
        source = " 첫 문장   입니다.\r\n\r\n\r\n둘째\t문단입니다. "
        self.assertEqual(
            normalize_source_text(source),
            "첫 문장 입니다.\n\n둘째 문단입니다.",
        )

    def test_empty_and_oversized_text_are_rejected(self):
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_text(" \n\t ")
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_text("가" * (MAX_SOURCE_TEXT_CHARS + 1))

    def test_text_pdf_is_extracted_in_memory(self):
        expected = "This is a normal text based PDF document."
        extracted = extract_pdf_text(
            build_text_pdf_bytes(expected),
            "notes.pdf",
        )
        self.assertIn(expected, extracted)

    def test_empty_pdf_is_rejected_as_unsupported(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        output = io.BytesIO()
        writer.write(output)

        with self.assertRaisesRegex(
            SourceMaterialValidationError,
            "스캔본이나 이미지 전용 PDF",
        ):
            extract_pdf_text(output.getvalue(), "scan.pdf")

    @patch("services.review_material_service.get_openai_client")
    def test_invalid_text_does_not_create_openai_client(self, mock_client):
        with self.assertRaises(SourceMaterialValidationError):
            generate_source_review_material(
                source_title="원본",
                course_name="Python",
                goal="기초 학습",
                current_level=3,
                source_text="   ",
            )
        mock_client.assert_not_called()


class SourceReviewMaterialTests(unittest.TestCase):
    def test_structured_result_converts_to_required_markdown(self):
        structured = SourceReviewMaterialDraft(
            title="정규화 복습",
            source_overview="데이터 중복을 줄이는 정규화를 다룹니다.",
            core_concepts=["함수 종속성", "정규형"],
            important_details=["부분 함수 종속성을 제거합니다."],
            caution_points=["무조건 테이블 수를 늘리는 작업은 아닙니다."],
            self_review_checklist=["정규화의 목적을 설명할 수 있다."],
            final_summary="중복과 이상 현상을 줄이기 위한 구조화 과정입니다.",
        )

        markdown = convert_source_review_to_markdown(structured)

        for heading in [
            "## 원본 개요",
            "## 핵심 개념",
            "## 중요 세부 내용",
            "## 자주 하는 오해와 주의점",
            "## 셀프 복습 체크리스트",
            "## 최종 요약",
        ]:
            self.assertIn(heading, markdown)
        self.assertIn("- [ ] 정규화의 목적을 설명할 수 있다.", markdown)

    def test_partial_save_failure_removes_new_source_row(self):
        supabase = FakeSupabase(fail_review_insert=True)
        material = ReviewMaterialDraft(
            title="복습 자료",
            content_markdown="## 원본 개요\n\n내용",
        )

        with self.assertRaisesRegex(RuntimeError, "새 원본 행을 정리"):
            save_source_review_material_bundle(
                supabase=supabase,
                user_id=USER_ID,
                plan_id=PLAN_ID,
                source_title="원본",
                material_type="text",
                source_text="원본 내용",
                material=material,
            )

        self.assertEqual(supabase.learning_materials, [])


if __name__ == "__main__":
    unittest.main()
