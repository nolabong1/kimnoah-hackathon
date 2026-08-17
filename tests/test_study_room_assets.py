import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.prepare_study_room_asset import (
    CANVAS_SIZE,
    THUMBNAIL_SIZE,
    prepare_overlay,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StudyRoomAssetTests(unittest.TestCase):
    def test_all_catalog_assets_match_dimensions_and_alpha_rules(self):
        from services.shop_catalog import SHOP_ITEM_CATALOG

        base_path = PROJECT_ROOT / "assets/study_room/base/room_default.webp"
        with Image.open(base_path) as base_image:
            self.assertEqual(base_image.size, CANVAS_SIZE)

        for item in SHOP_ITEM_CATALOG:
            with self.subTest(item_key=item.item_key):
                overlay_path = PROJECT_ROOT / item.overlay_path
                thumbnail_path = PROJECT_ROOT / item.thumbnail_path
                self.assertTrue(overlay_path.is_file())
                self.assertTrue(thumbnail_path.is_file())

                with Image.open(overlay_path) as overlay:
                    self.assertEqual(overlay.size, CANVAS_SIZE)
                    self.assertIn("A", overlay.getbands())
                    self.assertEqual(
                        overlay.getchannel("A").getextrema()[0],
                        0,
                    )

                with Image.open(thumbnail_path) as thumbnail:
                    self.assertEqual(thumbnail.size, THUMBNAIL_SIZE)

    def test_review_previews_match_room_canvas(self):
        preview_directory = PROJECT_ROOT / "assets/study_room/previews"
        preview_paths = sorted(preview_directory.glob("*.webp"))

        self.assertGreaterEqual(len(preview_paths), 3)
        for preview_path in preview_paths:
            with self.subTest(preview=preview_path.name):
                with Image.open(preview_path) as preview:
                    self.assertEqual(preview.size, CANVAS_SIZE)

    def test_exported_catalog_matches_python_catalog(self):
        import json

        from services.shop_catalog import SHOP_ITEM_CATALOG

        catalog_path = PROJECT_ROOT / "assets/study_room/catalog.json"
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))

        self.assertEqual(len(payload), len(SHOP_ITEM_CATALOG))
        self.assertEqual(
            {item["item_key"] for item in payload},
            {item.item_key for item in SHOP_ITEM_CATALOG},
        )

    def test_overlay_preparation_rejects_out_of_bounds_position(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_path = temporary_path / "source.png"
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(
                source_path
            )

            with self.assertRaises(ValueError):
                prepare_overlay(
                    source_path,
                    temporary_path / "overlay.png",
                    temporary_path / "thumbnail.webp",
                    target_width=300,
                    left=1500,
                    top=0,
                )


if __name__ == "__main__":
    unittest.main()
