import base64
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.shop_catalog import SHOP_ITEMS_BY_KEY


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_approved_shop_thumbnail_path(
    item: Mapping[str, Any],
) -> Path | None:
    """코드 카탈로그와 경로가 같은 실제 썸네일만 반환합니다."""

    item_key = item.get("item_key")
    definition = SHOP_ITEMS_BY_KEY.get(item_key)
    if definition is None:
        return None
    if item.get("thumbnail_path") != definition.thumbnail_path:
        return None
    candidate = PROJECT_ROOT / definition.thumbnail_path
    return candidate if candidate.is_file() else None


def get_approved_shop_thumbnail_data_url(
    item: Mapping[str, Any],
) -> str | None:
    """승인된 상점 썸네일을 브라우저 전달용 data URL로 변환합니다."""

    thumbnail_path = get_approved_shop_thumbnail_path(item)
    if thumbnail_path is None:
        return None
    return _thumbnail_path_to_data_url(str(thumbnail_path))


@lru_cache(maxsize=64)
def _thumbnail_path_to_data_url(path_value: str) -> str | None:
    path = Path(path_value)
    mime_type = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(path.suffix.casefold())
    if mime_type is None:
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
