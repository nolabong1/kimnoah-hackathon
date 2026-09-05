import re
import unittest

from services.pdf_visual_extraction_service import (
    PDF_VISUAL_EXTRACTION_PROMPT_VERSION,
)
from services.image_visual_extraction_service import (
    IMAGE_VISUAL_EXTRACTION_PROMPT_VERSION,
)
from services.learning_assessment_service import (
    LEARNING_ASSESSMENT_PROMPT_VERSION,
)
from services.mock_exam_service import MOCK_EXAM_PROMPT_VERSION
from services.quiz_service import QUIZ_PROMPT_VERSION
from services.review_material_service import (
    REVIEW_MATERIAL_PROMPT_VERSION,
    SOURCE_REVIEW_PROMPT_VERSION,
)
from services.study_plan_service import STUDY_PLAN_PROMPT_VERSION
from services.tutor_service import (
    TUTOR_FEEDBACK_PROMPT_VERSION,
    TUTOR_GUIDANCE_PROMPT_VERSION,
)
from services.weekly_review_service import WEEKLY_REVIEW_PROMPT_VERSION


class PromptVersionTests(unittest.TestCase):
    def test_all_ai_entry_points_have_stable_version_identifiers(self) -> None:
        versions = (
            STUDY_PLAN_PROMPT_VERSION,
            REVIEW_MATERIAL_PROMPT_VERSION,
            SOURCE_REVIEW_PROMPT_VERSION,
            QUIZ_PROMPT_VERSION,
            TUTOR_GUIDANCE_PROMPT_VERSION,
            TUTOR_FEEDBACK_PROMPT_VERSION,
            WEEKLY_REVIEW_PROMPT_VERSION,
            PDF_VISUAL_EXTRACTION_PROMPT_VERSION,
            IMAGE_VISUAL_EXTRACTION_PROMPT_VERSION,
            LEARNING_ASSESSMENT_PROMPT_VERSION,
            MOCK_EXAM_PROMPT_VERSION,
        )

        for version in versions:
            with self.subTest(version=version):
                self.assertRegex(version, re.compile(r"^[a-z0-9_]{3,100}$"))
        self.assertEqual(len(versions), len(set(versions)))


if __name__ == "__main__":
    unittest.main()
