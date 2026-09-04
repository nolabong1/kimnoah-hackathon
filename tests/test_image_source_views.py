import io
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from models.review_material import ReviewMaterialDraft
from models.tutor import TutorFinalSolution, TutorGuidance, TutorHint
from services.image_visual_extraction_service import (
    ImageExtractionItem,
    ImageExtractionResult,
)
from services.tutor_service import IMAGE_ONLY_QUESTION, TutorGenerationResult


USER_ID = "11111111-1111-4111-8111-111111111111"
PLAN_ID = "22222222-2222-4222-8222-222222222222"
OBJECTIVE_ID = "33333333-3333-4333-8333-333333333333"


def render_tutor_image_test_page(supabase, user):
    from views.tutor_view import render_tutor

    render_tutor(supabase, user)


def render_source_image_test_page(supabase, user):
    from views.source_review_material_view import render_source_review_material

    render_source_review_material(supabase, user)


def build_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(output, format="PNG")
    return output.getvalue()


def build_png_with_width(width: int) -> bytes:
    """중복 이미지 검증을 피하도록 폭이 다른 테스트 PNG를 만듭니다."""

    output = io.BytesIO()
    Image.new("RGB", (width, 480), "white").save(output, format="PNG")
    return output.getvalue()


def build_guidance() -> TutorGuidance:
    return TutorGuidance(
        problem_summary="이미지에 제시된 식을 푸는 문제입니다.",
        required_concepts=["등식의 성질"],
        hints=[
            TutorHint(
                level=level,
                title=f"힌트 {level}",
                content=f"{level}단계 접근을 생각하세요.",
                guiding_question="다음에 무엇을 확인해야 하나요?",
            )
            for level in (1, 2, 3)
        ],
        final_solution=TutorFinalSolution(
            final_answer="x = 3",
            reasoning_steps=["등식의 성질을 적용합니다."],
            why_solution_works="양변에 같은 연산을 적용했습니다.",
            common_mistakes=["부호를 잘못 바꾸는 실수"],
            self_check_question="원래 식에 대입하면 맞나요?",
        ),
    )


class ImageSourceViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "id": PLAN_ID,
            "title": "수학 7일 계획",
            "course_name": "수학",
            "goal": "일차방정식 익히기",
            "current_level": 3,
        }
        self.user = SimpleNamespace(id=USER_ID)

    def test_tutor_image_starts_once_without_text_question(self) -> None:
        guidance = build_guidance()
        generation_result = TutorGenerationResult(
            guidance=guidance,
            reference_context=None,
            reference_was_limited=False,
            resolved_question=IMAGE_ONLY_QUESTION,
        )
        app = AppTest.from_function(
            render_tutor_image_test_page,
            args=(object(), self.user),
        )

        with (
            patch(
                "views.tutor_view.get_user_study_plans",
                return_value=[self.plan],
            ),
            patch("views.tutor_view.get_study_plan_tasks", return_value=[]),
            patch(
                "views.tutor_view.get_learning_materials_by_plan",
                return_value=[],
            ),
            patch(
                "views.tutor_view.get_review_materials_by_plan",
                return_value=[],
            ),
            patch(
                "views.tutor_view.generate_tutor_guidance",
                return_value=generation_result,
            ) as generate_guidance,
        ):
            app.run()
            app.file_uploader[0].set_value(
                [
                    ("problem-1.png", build_png(), "image/png"),
                    (
                        "problem-2.png",
                        build_png_with_width(650),
                        "image/png",
                    ),
                ]
            )
            start_button = next(
                button
                for button in app.button
                if button.label == "AI 튜터 시작하기"
            )
            start_button.click().run()
            next_hint_button = next(
                button
                for button in app.button
                if button.label == "다음 힌트"
            )
            next_hint_button.click().run()

        self.assertEqual(list(app.exception), [])
        generate_guidance.assert_called_once()
        self.assertEqual(
            len(generate_guidance.call_args.kwargs["problem_images"]),
            2,
        )
        self.assertIn(
            IMAGE_ONLY_QUESTION,
            [item.value for item in app.markdown],
        )
        self.assertIn(
            "2단계 접근을 생각하세요.",
            [item.value for item in app.markdown],
        )

    def test_source_image_is_extracted_then_saved_as_image(self) -> None:
        generated_material = ReviewMaterialDraft(
            title="이미지 복습자료",
            content_markdown="## 원본 개요\n\n이미지 내용",
        )
        saved_bundle = {
            "source_material": {"id": "source-id"},
            "review_material": {
                "id": "review-id",
                "title": generated_material.title,
                "content_markdown": generated_material.content_markdown,
            },
        }
        objective = SimpleNamespace(id=OBJECTIVE_ID, title="방정식 풀이")
        app = AppTest.from_function(
            render_source_image_test_page,
            args=(object(), self.user),
        )

        with (
            patch(
                "views.source_review_material_view.get_user_study_plans",
                return_value=[self.plan],
            ),
            patch(
                "views.source_review_material_view."
                "get_learning_objectives_by_plan_ids",
                return_value={PLAN_ID: [objective]},
            ),
            patch(
                "views.source_review_material_view.load_learner_context",
                return_value=None,
            ),
            patch(
                "views.source_review_material_view.extract_images_with_ai_vision",
                return_value=ImageExtractionResult(
                    text=(
                        "[이미지 1: notes-1.png]\n\n2x + 2 = 8\n\n"
                        "[이미지 2: notes-2.png]\n\n양변에서 2를 뺍니다."
                    ),
                    images=(
                        ImageExtractionItem(
                            filename="notes-1.png",
                            width=640,
                            height=480,
                        ),
                        ImageExtractionItem(
                            filename="notes-2.png",
                            width=650,
                            height=480,
                        ),
                    ),
                ),
            ) as extract_image,
            patch(
                "views.source_review_material_view."
                "generate_source_review_material",
                return_value=generated_material,
            ) as generate_material,
            patch(
                "views.source_review_material_view."
                "save_source_review_material_bundle",
                return_value=saved_bundle,
            ) as save_bundle,
        ):
            app.run()
            app.segmented_control[1].set_value("image").run()
            app.text_input[0].set_value("방정식 필기")
            app.file_uploader[0].set_value(
                [
                    ("notes-1.png", build_png(), "image/png"),
                    (
                        "notes-2.png",
                        build_png_with_width(650),
                        "image/png",
                    ),
                ]
            )
            generate_button = next(
                button
                for button in app.button
                if button.label == "AI 복습 자료 생성하기"
            )
            generate_button.click().run()

        self.assertEqual(list(app.exception), [])
        extract_image.assert_called_once()
        generate_material.assert_called_once()
        save_bundle.assert_called_once_with(
            supabase=ANY,
            user_id=USER_ID,
            plan_id=PLAN_ID,
            source_title="방정식 필기",
            material_type="image",
            source_text=(
                "[이미지 1: notes-1.png]\n\n2x + 2 = 8\n\n"
                "[이미지 2: notes-2.png]\n\n양변에서 2를 뺍니다."
            ),
            material=generated_material,
            learning_objective_id=OBJECTIVE_ID,
        )


if __name__ == "__main__":
    unittest.main()
