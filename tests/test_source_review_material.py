import io
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfWriter

from models.review_material import (
    ReviewMaterialDraft,
    SourceGroundedPoint,
    SourceRecallQuestion,
    SourceReviewMaterialDraft,
)
from services.review_material_repository import (
    _build_source_review_material_bundles,
    get_source_review_material_bundles_by_plan,
    save_source_review_material_bundle,
)
from services.review_material_service import (
    convert_source_review_to_markdown,
    estimate_source_review_ai_calls,
    find_source_evidence_page,
    generate_source_review_material,
)
from services.source_material_service import (
    MAX_DIRECT_SOURCE_TEXT_CHARS,
    MAX_SOURCE_CHUNK_CHARS,
    MAX_SOURCE_TEXT_CHARS,
    SourceMaterialValidationError,
    _normalize_pdf_page_text,
    _remove_repeated_page_edges,
    extract_pdf_document,
    extract_pdf_text,
    normalize_source_text,
    split_source_text,
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


class FakeResponses:
    def __init__(self, parsed_outputs):
        self.parsed_outputs = list(parsed_outputs)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.parsed_outputs.pop(0)
        )


class FakeOpenAIClient:
    def __init__(self, parsed_outputs):
        self.responses = FakeResponses(parsed_outputs)


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
        self.assertEqual(
            validate_source_title("\x00강의\u0007 노트"),
            "강의 노트",
        )
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

    def test_text_normalization_removes_database_unsafe_controls(self):
        source = "PDF\x00원문\u0007 제어문자\n다음 문단"

        normalized = normalize_source_text(source)

        self.assertEqual(
            normalized,
            "PDF원문 제어문자\n다음 문단",
        )
        self.assertNotIn("\x00", normalized)

    def test_empty_and_oversized_text_are_rejected(self):
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_text(" \n\t ")
        with self.assertRaises(SourceMaterialValidationError):
            validate_source_text("가" * (MAX_SOURCE_TEXT_CHARS + 1))

    def test_long_source_is_split_deterministically_without_oversized_chunk(self):
        source = "\n\n".join(
            f"[페이지 {index}]\n{index}번째 핵심 문장 " + ("가" * 1500)
            for index in range(1, 25)
        )

        first_chunks = split_source_text(source)
        second_chunks = split_source_text(source)

        self.assertEqual(first_chunks, second_chunks)
        self.assertGreater(len(first_chunks), 1)
        self.assertTrue(
            all(
                len(chunk) <= MAX_SOURCE_CHUNK_CHARS
                for chunk in first_chunks
            )
        )
        for index in range(1, 25):
            self.assertTrue(
                any(
                    f"{index}번째 핵심 문장" in chunk
                    for chunk in first_chunks
                )
            )

    def test_text_pdf_is_extracted_in_memory(self):
        expected = "This is a normal text based PDF document."
        extracted = extract_pdf_text(
            build_text_pdf_bytes(expected),
            "notes.pdf",
        )
        self.assertIn(expected, extracted)
        self.assertIn("[페이지 1]", extracted)

    def test_pdf_extraction_returns_page_quality_summary(self):
        result = extract_pdf_document(
            build_text_pdf_bytes("Readable PDF source text for review."),
            "notes.pdf",
        )

        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.extracted_page_count, 1)
        self.assertNotIn("text", result.to_summary())

    def test_pdf_cleanup_joins_hyphen_and_removes_repeated_edges(self):
        self.assertEqual(
            _normalize_pdf_page_text("inter-\noperability"),
            "interoperability",
        )
        cleaned_pages, removed_count = _remove_repeated_page_edges(
            [
                (1, "공통 강의 노트\n첫 페이지 핵심 내용\n1"),
                (2, "공통 강의 노트\n둘째 페이지 핵심 내용\n2"),
            ]
        )

        self.assertEqual(removed_count, 4)
        self.assertEqual(
            cleaned_pages,
            [
                (1, "첫 페이지 핵심 내용"),
                (2, "둘째 페이지 핵심 내용"),
            ],
        )

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
    @staticmethod
    def build_structured_review(
        source_evidence: str = "정규화는 데이터 중복을 줄입니다.",
    ) -> SourceReviewMaterialDraft:
        return SourceReviewMaterialDraft(
            title="정규화 복습",
            source_overview="데이터 중복을 줄이는 정규화를 다룹니다.",
            core_concepts=[
                SourceGroundedPoint(
                    content="정규화는 데이터 중복을 줄입니다.",
                    source_evidence=source_evidence,
                )
            ],
            important_details=[
                SourceGroundedPoint(
                    content="부분 함수 종속성을 제거합니다.",
                    source_evidence="부분 함수 종속성을 제거합니다.",
                )
            ],
            caution_points=[],
            self_review_checklist=["정규화의 목적을 설명할 수 있다."],
            active_recall_questions=[
                SourceRecallQuestion(
                    question="정규화의 목적은 무엇인가요?",
                    answer="데이터 중복을 줄이는 것입니다.",
                    source_evidence="정규화는 데이터 중복을 줄입니다.",
                ),
                SourceRecallQuestion(
                    question="제거해야 하는 종속성은 무엇인가요?",
                    answer="부분 함수 종속성입니다.",
                    source_evidence="부분 함수 종속성을 제거합니다.",
                ),
            ],
            final_summary="중복과 이상 현상을 줄이기 위한 구조화 과정입니다.",
        )

    def test_structured_result_converts_to_required_markdown(self):
        structured = self.build_structured_review()
        source_text = (
            "[페이지 2]\n정규화는 데이터 중복을 줄입니다.\n"
            "부분 함수 종속성을 제거합니다."
        )

        markdown = convert_source_review_to_markdown(
            structured,
            source_text,
        )

        for heading in [
            "## 원본 개요",
            "## 핵심 개념",
            "## 중요 세부 내용",
            "## 자주 하는 오해와 주의점",
            "## 셀프 복습 체크리스트",
            "## 능동 회상 문제",
            "## 최종 요약",
        ]:
            self.assertIn(heading, markdown)
        self.assertIn("- [ ] 정규화의 목적을 설명할 수 있다.", markdown)
        self.assertIn("원문 근거 · 2페이지", markdown)
        self.assertEqual(
            find_source_evidence_page(
                source_text,
                "정규화는 데이터 중복을 줄입니다.",
            ),
            2,
        )

    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_grounded_review_retries_unsupported_evidence(
        self,
        get_client,
        _get_model,
    ):
        invalid_review = self.build_structured_review(
            "원본에 없는 근거 문장입니다."
        )
        valid_review = self.build_structured_review()
        fake_client = FakeOpenAIClient(
            [invalid_review, valid_review]
        )
        get_client.return_value = fake_client
        source_text = (
            "정규화는 데이터 중복을 줄입니다. "
            "부분 함수 종속성을 제거합니다."
        )

        result = generate_source_review_material(
            source_title="정규화 원본",
            course_name="데이터베이스",
            goal="정규화를 이해한다.",
            current_level=3,
            source_text=source_text,
            learner_context={
                "course_key": "데이터베이스",
                "evaluated_concept_count": 1,
                "weak_concept_count": 1,
                "average_mastery_score": 50,
                "focus_concepts": [
                    {
                        "concept_key": "normalization",
                        "concept_name": "정규화",
                        "mastery_score": 50,
                        "correct_count": 0,
                        "incorrect_count": 2,
                        "consecutive_incorrect_count": 2,
                        "recent_result": "incorrect",
                        "is_weak": True,
                        "repeated_diagnoses": [],
                    }
                ],
                "stable_concepts": [],
            },
        )

        self.assertEqual(len(fake_client.responses.calls), 2)
        request_payload = json.loads(
            fake_client.responses.calls[0]["input"][1]["content"]
        )
        self.assertIn("learner_context", request_payload)
        self.assertIn("## 능동 회상 문제", result.content_markdown)

    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_grounded_review_restores_pdf_punctuation_to_source_text(
        self,
        get_client,
        _get_model,
    ):
        structured_review = self.build_structured_review()
        normalized_evidence = (
            "정규화(正規化)는 데이터 중복을 줄입니다"
        )
        structured_review.core_concepts[0].source_evidence = (
            normalized_evidence
        )
        structured_review.active_recall_questions[
            0
        ].source_evidence = normalized_evidence
        fake_client = FakeOpenAIClient([structured_review])
        get_client.return_value = fake_client
        source_evidence = (
            "정규화（正規化）는 “데이터 중복”을 줄입니다"
        )
        source_text = (
            f"[페이지 1]\n{source_evidence}.\n"
            "부분 함수 종속성을 제거합니다."
        )

        result = generate_source_review_material(
            source_title="PDF 정규화 원본",
            course_name="데이터베이스",
            goal="정규화를 이해한다.",
            current_level=3,
            source_text=source_text,
        )

        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertIn(
            f"> 원문 근거 · 1페이지: {source_evidence}",
            result.content_markdown,
        )

    @patch("services.review_material_service.get_openai_model")
    @patch("services.review_material_service.get_openai_client")
    def test_long_source_uses_chunk_analysis_then_synthesis(
        self,
        get_client,
        _get_model,
    ):
        repeated_source = (
            "정규화는 데이터 중복을 줄입니다. "
            "부분 함수 종속성을 제거합니다. "
        )
        source_text = repeated_source * (
            MAX_DIRECT_SOURCE_TEXT_CHARS // len(repeated_source) + 100
        )
        expected_calls = estimate_source_review_ai_calls(source_text)
        structured_review = self.build_structured_review()
        fake_client = FakeOpenAIClient(
            [structured_review] * expected_calls
        )
        get_client.return_value = fake_client

        result = generate_source_review_material(
            source_title="긴 정규화 원본",
            course_name="데이터베이스",
            goal="정규화를 이해한다.",
            current_level=3,
            source_text=source_text,
        )

        self.assertEqual(
            len(fake_client.responses.calls),
            expected_calls,
        )
        synthesis_payload = json.loads(
            fake_client.responses.calls[-1]["input"][1]["content"]
        )
        self.assertEqual(
            len(synthesis_payload["partial_reviews"]),
            expected_calls - 1,
        )
        self.assertNotIn("source_text", synthesis_payload)
        self.assertIn("## 능동 회상 문제", result.content_markdown)

    def test_bundle_removes_nulls_at_database_boundary(self):
        supabase = FakeSupabase()
        material = ReviewMaterialDraft(
            title="복습\x00 자료",
            content_markdown="## 원본 개요\n\n복습\x00 내용",
        )

        saved_bundle = save_source_review_material_bundle(
            supabase=supabase,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            source_title="원본\x00 제목",
            material_type="pdf",
            source_text="PDF\x00 원본 내용",
            material=material,
        )

        self.assertNotIn(
            "\x00",
            saved_bundle["source_material"]["title"],
        )
        self.assertNotIn(
            "\x00",
            saved_bundle["source_material"]["content_text"],
        )
        self.assertNotIn(
            "\x00",
            saved_bundle["review_material"]["title"],
        )
        self.assertNotIn(
            "\x00",
            saved_bundle["review_material"]["content_markdown"],
        )

    def test_archive_bundles_only_owned_source_linked_reviews(self):
        valid_source = {
            "id": SOURCE_ID,
            "user_id": USER_ID,
            "plan_id": PLAN_ID,
            "title": "PDF 원본",
        }
        review_materials = [
            {
                "id": "valid-review",
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "source_material_id": SOURCE_ID,
            },
            {
                "id": "task-review",
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "source_material_id": None,
            },
            {
                "id": "other-user-review",
                "user_id": "other-user",
                "plan_id": PLAN_ID,
                "source_material_id": SOURCE_ID,
            },
            {
                "id": "missing-source-review",
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "source_material_id": "missing-source",
            },
        ]

        bundles = _build_source_review_material_bundles(
            learning_materials=[
                valid_source,
                {
                    "id": "other-plan-source",
                    "user_id": USER_ID,
                    "plan_id": "other-plan",
                },
            ],
            review_materials=review_materials,
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        self.assertEqual(len(bundles), 1)
        self.assertEqual(
            bundles[0]["review_material"]["id"],
            "valid-review",
        )
        self.assertEqual(bundles[0]["source_material"], valid_source)

    def test_archive_query_uses_source_metadata_and_linked_ids_only(self):
        source_row = {
            "id": SOURCE_ID,
            "user_id": USER_ID,
            "plan_id": PLAN_ID,
            "title": "PDF 원본",
            "material_type": "pdf",
        }
        review_row = {
            "id": "review-id",
            "user_id": USER_ID,
            "plan_id": PLAN_ID,
            "source_material_id": SOURCE_ID,
            "title": "복습자료",
            "content_markdown": "## 복습",
        }
        source_request = MagicMock()
        review_request = MagicMock()
        for request in (source_request, review_request):
            request.select.return_value = request
            request.eq.return_value = request
            request.in_.return_value = request
            request.order.return_value = request
        source_request.execute.return_value = FakeResponse([source_row])
        review_request.execute.return_value = FakeResponse([review_row])
        supabase = MagicMock()
        supabase.table.side_effect = (
            lambda table_name: source_request
            if table_name == "learning_materials"
            else review_request
        )

        bundles = get_source_review_material_bundles_by_plan(
            supabase=supabase,
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        selected_source_fields = source_request.select.call_args.args[0]
        self.assertNotIn("content_text", selected_source_fields)
        review_request.in_.assert_called_once_with(
            "source_material_id",
            [SOURCE_ID],
        )
        self.assertEqual(
            bundles[0]["review_material"]["id"],
            "review-id",
        )

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
