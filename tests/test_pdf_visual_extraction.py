import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter

from models.source_material import VisualPdfExtraction
from services.pdf_visual_extraction_service import (
    MAX_VISUAL_PDF_PAGES,
    extract_pdf_with_ai_vision,
)
from services.source_material_service import SourceMaterialValidationError


def build_blank_pdf(page_count: int) -> bytes:
    """파일 입력 계약 검사에 사용할 메모리 PDF를 만듭니다."""

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeResponses:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed_output)


class FakeOpenAIClient:
    def __init__(self, parsed_output):
        self.responses = FakeResponses(parsed_output)


class VisualPdfExtractionTests(unittest.TestCase):
    @patch(
        "services.pdf_visual_extraction_service.get_openai_model",
        return_value="gpt-test",
    )
    @patch("services.pdf_visual_extraction_service.get_openai_client")
    def test_pdf_is_sent_once_as_high_detail_file_input(
        self,
        get_client,
        _get_model,
    ):
        parsed_output = VisualPdfExtraction.model_validate(
            {
                "pages": [
                    {
                        "page_number": 1,
                        "content_text": "정규화는 데이터 중복을 줄입니다.",
                        "visual_notes": [
                            "표는 제1정규형부터 제3정규형까지 비교합니다."
                        ],
                    }
                ],
                "extraction_warnings": [],
            }
        )
        fake_client = FakeOpenAIClient(parsed_output)
        get_client.return_value = fake_client

        result = extract_pdf_with_ai_vision(
            build_blank_pdf(1),
            "scan.pdf",
        )

        self.assertEqual(len(fake_client.responses.calls), 1)
        request = fake_client.responses.calls[0]
        self.assertFalse(request["store"])
        file_input = request["input"][1]["content"][0]
        self.assertEqual(file_input["type"], "input_file")
        self.assertEqual(file_input["detail"], "high")
        self.assertTrue(
            file_input["file_data"].startswith(
                "data:application/pdf;base64,"
            )
        )
        self.assertIn("[페이지 1]", result.text)
        self.assertIn("시각 자료 관찰", result.text)
        self.assertNotIn("text", result.to_summary())

    @patch("services.pdf_visual_extraction_service.get_openai_client")
    def test_page_limit_is_rejected_before_openai_client(self, get_client):
        with self.assertRaisesRegex(
            SourceMaterialValidationError,
            f"최대 {MAX_VISUAL_PDF_PAGES}페이지",
        ):
            extract_pdf_with_ai_vision(
                build_blank_pdf(MAX_VISUAL_PDF_PAGES + 1),
                "long-scan.pdf",
            )

        get_client.assert_not_called()

    @patch(
        "services.pdf_visual_extraction_service.get_openai_model",
        return_value="gpt-test",
    )
    @patch("services.pdf_visual_extraction_service.get_openai_client")
    def test_out_of_range_page_number_is_rejected(
        self,
        get_client,
        _get_model,
    ):
        get_client.return_value = FakeOpenAIClient(
            VisualPdfExtraction.model_validate(
                {
                    "pages": [
                        {
                            "page_number": 2,
                            "content_text": "존재하지 않는 페이지입니다.",
                            "visual_notes": [],
                        }
                    ],
                    "extraction_warnings": [],
                }
            )
        )

        with self.assertRaisesRegex(RuntimeError, "페이지 번호"):
            extract_pdf_with_ai_vision(
                build_blank_pdf(1),
                "scan.pdf",
            )


if __name__ == "__main__":
    unittest.main()
