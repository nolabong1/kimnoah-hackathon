import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_CURSOR_ASSET_PATH = PROJECT_ROOT / "assets" / "ui" / "game_cursor.png"
CURSOR_HOTSPOT_X = 5
CURSOR_HOTSPOT_Y = 2
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@lru_cache(maxsize=1)
def load_site_cursor_data_url(
    asset_path: Path = SITE_CURSOR_ASSET_PATH,
) -> str:
    """검증된 로컬 PNG 커서를 브라우저용 data URL로 변환합니다."""

    image_bytes = asset_path.read_bytes()
    if not image_bytes.startswith(PNG_SIGNATURE):
        raise ValueError("사이트 커서 에셋이 올바른 PNG 파일이 아닙니다.")
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded_image}"


def build_site_cursor_css(cursor_data_url: str) -> str:
    """기본 조작성을 보존한 전역 게임풍 커서 CSS를 만듭니다."""

    if not cursor_data_url.startswith("data:image/png;base64,"):
        raise ValueError("사이트 커서 data URL이 올바르지 않습니다.")

    cursor = (
        f'url("{cursor_data_url}") '
        f"{CURSOR_HOTSPOT_X} {CURSOR_HOTSPOT_Y}"
    )
    return f"""
<style>
.stApp,
.stApp * {{
  cursor: {cursor}, auto !important;
}}

.stApp a,
.stApp button,
.stApp [role="button"],
.stApp [role="link"],
.stApp label[for] {{
  cursor: {cursor}, pointer !important;
}}

.stApp input[type="email"],
.stApp input[type="number"],
.stApp input[type="password"],
.stApp input[type="search"],
.stApp input[type="text"],
.stApp textarea,
.stApp [contenteditable="true"] {{
  cursor: text !important;
}}

.stApp :disabled,
.stApp [aria-disabled="true"] {{
  cursor: not-allowed !important;
}}
</style>
""".strip()


def apply_site_cursor() -> bool:
    """전역 커서를 적용하고 에셋을 읽지 못하면 기본 커서를 유지합니다."""

    try:
        cursor_data_url = load_site_cursor_data_url(SITE_CURSOR_ASSET_PATH)
        st.html(build_site_cursor_css(cursor_data_url))
    except (OSError, ValueError):
        return False
    return True
