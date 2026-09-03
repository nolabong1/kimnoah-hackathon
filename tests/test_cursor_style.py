import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from views.cursor_style import (
    CURSOR_HOTSPOT_X,
    CURSOR_HOTSPOT_Y,
    SITE_CURSOR_ASSET_PATH,
    apply_site_cursor,
    build_site_cursor_css,
    load_site_cursor_data_url,
)


class CursorStyleTests(unittest.TestCase):
    def tearDown(self):
        load_site_cursor_data_url.cache_clear()

    def test_cursor_asset_is_compact_transparent_png(self):
        with Image.open(SITE_CURSOR_ASSET_PATH) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGBA")
            self.assertLessEqual(image.width, 48)
            self.assertLessEqual(image.height, 48)
            self.assertEqual(image.getextrema()[3][0], 0)
            self.assertGreater(image.getextrema()[3][1], 0)

    def test_cursor_css_uses_hotspot_and_preserves_input_states(self):
        data_url = load_site_cursor_data_url()

        css = build_site_cursor_css(data_url)

        self.assertIn(
            f") {CURSOR_HOTSPOT_X} {CURSOR_HOTSPOT_Y}, auto",
            css,
        )
        self.assertIn("cursor: text !important", css)
        self.assertIn("cursor: not-allowed !important", css)
        self.assertNotIn(str(SITE_CURSOR_ASSET_PATH), css)

    @patch("views.cursor_style.st.html")
    def test_apply_site_cursor_renders_local_asset_css(self, render_html):
        applied = apply_site_cursor()

        self.assertTrue(applied)
        rendered_css = render_html.call_args.args[0]
        self.assertIn("data:image/png;base64,", rendered_css)
        self.assertIn(".stApp", rendered_css)

    @patch("views.cursor_style.st.html")
    def test_missing_cursor_asset_keeps_browser_default(self, render_html):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.png"
            with patch(
                "views.cursor_style.SITE_CURSOR_ASSET_PATH",
                missing_path,
            ):
                load_site_cursor_data_url.cache_clear()
                applied = apply_site_cursor()

        self.assertFalse(applied)
        render_html.assert_not_called()


if __name__ == "__main__":
    unittest.main()
