import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from models.source_material import (
    VisualImageBatchExtraction,
    VisualImageExtraction,
)
from services.image_input_service import (
    AI_IMAGE_MAX_DIMENSION,
    MAX_IMAGE_COUNT,
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_TOTAL_IMAGE_UPLOAD_BYTES,
    ImageInputValidationError,
    build_input_image_content,
    prepare_image_for_ai,
    prepare_images_for_ai,
    restore_prepared_image,
    restore_prepared_images,
)
from services.image_visual_extraction_service import (
    extract_images_with_ai_vision,
)


def build_image_bytes(
    *,
    width: int = 640,
    height: int = 480,
    image_format: str = "PNG",
) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(
        output,
        format=image_format,
    )
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


class ImageInputTests(unittest.TestCase):
    def test_valid_image_is_reencoded_and_restored(self) -> None:
        prepared = prepare_image_for_ai(
            build_image_bytes(),
            "problem.png",
            "image/png",
        )

        self.assertEqual(prepared.mime_type, "image/png")
        self.assertTrue(prepared.data_url.startswith("data:image/png;base64,"))
        encoded = prepared.data_url.split(",", 1)[1]
        self.assertEqual(len(base64.b64decode(encoded)), prepared.prepared_size_bytes)
        self.assertEqual(
            restore_prepared_image(prepared.to_session_payload()),
            prepared,
        )
        self.assertEqual(
            build_input_image_content(prepared)["detail"],
            "high",
        )

    def test_large_dimensions_are_reduced_deterministically(self) -> None:
        source = build_image_bytes(width=3_000, height=1_500)
        first = prepare_image_for_ai(source, "wide.png", "image/png")
        second = prepare_image_for_ai(source, "wide.png", "image/png")

        self.assertEqual(first.width, AI_IMAGE_MAX_DIMENSION)
        self.assertEqual(first.height, AI_IMAGE_MAX_DIMENSION // 2)
        self.assertEqual(first.sha256, second.sha256)

    def test_empty_oversized_and_disguised_files_are_rejected(self) -> None:
        invalid_cases = (
            (b"", "empty.png", "image/png"),
            (b"x" * (MAX_IMAGE_UPLOAD_BYTES + 1), "large.png", "image/png"),
            (b"not an image", "fake.png", "image/png"),
            (build_image_bytes(), "fake.pdf", "application/pdf"),
            (build_image_bytes(), "fake.jpg", "image/jpeg"),
        )
        for image_bytes, filename, mime_type in invalid_cases:
            with self.subTest(filename=filename), self.assertRaises(
                ImageInputValidationError
            ):
                prepare_image_for_ai(image_bytes, filename, mime_type)

    def test_tampered_session_image_is_rejected(self) -> None:
        prepared = prepare_image_for_ai(
            build_image_bytes(),
            "problem.png",
            "image/png",
        )
        payload = prepared.to_session_payload()
        payload["data_url"] += "AAAA"

        with self.assertRaises(ImageInputValidationError):
            restore_prepared_image(payload)

    def test_image_batch_preserves_order_and_restores(self) -> None:
        expected_widths = [640 + index for index in range(MAX_IMAGE_COUNT)]
        prepared_images = prepare_images_for_ai(
            [
                (
                    build_image_bytes(width=width),
                    f"image-{index + 1}.png",
                    "image/png",
                )
                for index, width in enumerate(expected_widths)
            ]
        )

        self.assertEqual(
            [image.width for image in prepared_images],
            expected_widths,
        )
        restored = restore_prepared_images(
            [image.to_session_payload() for image in prepared_images]
        )
        self.assertEqual(restored, prepared_images)

    def test_image_batch_rejects_count_total_size_and_duplicates(self) -> None:
        valid_image = build_image_bytes()
        with self.assertRaises(ImageInputValidationError):
            prepare_images_for_ai(
                [
                    (valid_image, f"image-{index}.png", "image/png")
                    for index in range(MAX_IMAGE_COUNT + 1)
                ]
            )
        oversized_part = b"x" * (
            MAX_TOTAL_IMAGE_UPLOAD_BYTES // MAX_IMAGE_COUNT + 1
        )
        with self.assertRaises(ImageInputValidationError):
            prepare_images_for_ai(
                [
                    (oversized_part, f"large-{index}.png", "image/png")
                    for index in range(MAX_IMAGE_COUNT)
                ]
            )
        with self.assertRaises(ImageInputValidationError):
            prepare_images_for_ai(
                [
                    (valid_image, "first.png", "image/png"),
                    (valid_image, "duplicate.png", "image/png"),
                ]
            )

    @patch(
        "services.image_visual_extraction_service.get_openai_model",
        return_value="test-model",
    )
    @patch("services.image_visual_extraction_service.get_openai_client")
    def test_visual_extraction_uses_one_nonstored_image_request(
        self,
        mock_client,
        _mock_model,
    ) -> None:
        parsed = VisualImageBatchExtraction(
            images=[
                VisualImageExtraction(
                    image_number=1,
                    content_text="삼각형의 밑변은 4이고 높이는 3입니다.",
                    visual_notes=["밑변과 높이가 직각으로 표시되어 있습니다."],
                    extraction_warnings=[],
                ),
                VisualImageExtraction(
                    image_number=2,
                    content_text="삼각형의 넓이를 구하세요.",
                    visual_notes=[],
                    extraction_warnings=[],
                ),
            ]
        )
        fake_client = FakeOpenAIClient(parsed)
        mock_client.return_value = fake_client
        prepared_images = prepare_images_for_ai(
            [
                (build_image_bytes(width=640), "geometry-1.png", "image/png"),
                (build_image_bytes(width=650), "geometry-2.png", "image/png"),
            ]
        )

        result = extract_images_with_ai_vision(
            prepared_images,
            ["geometry-1.png", "geometry-2.png"],
        )

        self.assertIn("[이미지 1: geometry-1.png]", result.text)
        self.assertIn("[이미지 2: geometry-2.png]", result.text)
        self.assertIn("삼각형의 밑변", result.text)
        self.assertEqual(result.to_summary()["image_count"], 2)
        self.assertEqual(len(fake_client.responses.calls), 1)
        request = fake_client.responses.calls[0]
        self.assertFalse(request["store"])
        user_content = request["input"][1]["content"]
        self.assertEqual(
            [content["type"] for content in user_content],
            ["input_image", "input_image", "input_text"],
        )
        self.assertTrue(
            all(content["detail"] == "high" for content in user_content[:2])
        )

    @patch(
        "services.image_visual_extraction_service.get_openai_model",
        return_value="test-model",
    )
    @patch("services.image_visual_extraction_service.get_openai_client")
    def test_visual_only_diagram_can_become_source_text(
        self,
        mock_client,
        _mock_model,
    ) -> None:
        fake_client = FakeOpenAIClient(
            VisualImageBatchExtraction(
                images=[
                    VisualImageExtraction(
                        image_number=1,
                        content_text="",
                        visual_notes=[
                            "막대그래프에서 A 항목은 30이고 B 항목은 20으로 표시됩니다."
                        ],
                        extraction_warnings=[],
                    )
                ]
            )
        )
        mock_client.return_value = fake_client
        prepared = prepare_image_for_ai(
            build_image_bytes(),
            "chart.png",
            "image/png",
        )

        result = extract_images_with_ai_vision([prepared], ["chart.png"])

        self.assertIn("시각 자료 관찰", result.text)
        self.assertIn("A 항목은 30", result.text)


if __name__ == "__main__":
    unittest.main()
