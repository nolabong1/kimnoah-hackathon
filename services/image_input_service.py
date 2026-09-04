import base64
import binascii
import hashlib
import io
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_UPLOAD_BYTES: Final[int] = 5 * 1024 * 1024
MAX_IMAGE_COUNT: Final[int] = 8
MAX_TOTAL_IMAGE_UPLOAD_BYTES: Final[int] = 15 * 1024 * 1024
MAX_PREPARED_IMAGE_BYTES: Final[int] = 10 * 1024 * 1024
MAX_TOTAL_PREPARED_IMAGE_BYTES: Final[int] = 20 * 1024 * 1024
MAX_IMAGE_INPUT_PIXELS: Final[int] = 24_000_000
AI_IMAGE_MAX_DIMENSION: Final[int] = 2_048
MIN_IMAGE_DIMENSION: Final[int] = 32
SUPPORTED_IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)
SUPPORTED_IMAGE_FORMAT_MIME_TYPES: Final[dict[str, str]] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
SUPPORTED_IMAGE_EXTENSION_FORMATS: Final[dict[str, str]] = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
}


class ImageInputValidationError(ValueError):
    """업로드 이미지가 안전한 AI 입력 규칙을 만족하지 못했습니다."""


@dataclass(frozen=True)
class PreparedImageInput:
    """메타데이터를 제거하고 AI 입력용으로 정규화한 이미지입니다."""

    data_url: str
    mime_type: str
    width: int
    height: int
    original_size_bytes: int
    prepared_size_bytes: int
    sha256: str

    def to_session_payload(self) -> dict[str, Any]:
        """Streamlit 세션에 저장할 독립 payload를 반환합니다."""

        return asdict(self)


def _validate_image_filename(filename: str) -> tuple[str, str]:
    """허용된 이미지 확장자를 검사하고 정리된 파일명을 반환합니다."""

    cleaned_filename = Path(filename).name.strip()
    if not cleaned_filename:
        raise ImageInputValidationError("이미지 파일 이름이 올바르지 않습니다.")
    extension = Path(cleaned_filename).suffix.casefold()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ImageInputValidationError(
            "PNG, JPG/JPEG 또는 WEBP 이미지만 사용할 수 있습니다."
        )
    return cleaned_filename, SUPPORTED_IMAGE_EXTENSION_FORMATS[extension]


def _validate_declared_mime_type(mime_type: str | None) -> None:
    """브라우저가 전달한 MIME 유형이 허용 목록에 있는지 확인합니다."""

    if mime_type is None:
        return
    if mime_type.casefold() not in set(
        SUPPORTED_IMAGE_FORMAT_MIME_TYPES.values()
    ):
        raise ImageInputValidationError(
            "PNG, JPG/JPEG 또는 WEBP 이미지만 사용할 수 있습니다."
        )


def _save_normalized_image(image: Image.Image, image_format: str) -> bytes:
    """EXIF 등 원본 메타데이터 없이 지원 형식으로 다시 인코딩합니다."""

    output = io.BytesIO()
    if image_format == "JPEG":
        normalized_image = image.convert("RGB")
        normalized_image.save(
            output,
            format="JPEG",
            quality=92,
            optimize=True,
        )
    elif image_format == "WEBP":
        normalized_image = image.convert(
            "RGBA" if image.mode in {"RGBA", "LA"} else "RGB"
        )
        normalized_image.save(
            output,
            format="WEBP",
            quality=92,
            method=4,
        )
    else:
        normalized_image = image.convert(
            "RGBA" if image.mode in {"RGBA", "LA"} else "RGB"
        )
        normalized_image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def prepare_image_for_ai(
    image_bytes: bytes,
    filename: str,
    declared_mime_type: str | None = None,
) -> PreparedImageInput:
    """이미지를 검증·축소·재인코딩해 안전한 AI 입력으로 준비합니다."""

    _cleaned_filename, expected_format = _validate_image_filename(filename)
    _validate_declared_mime_type(declared_mime_type)
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ImageInputValidationError("비어 있는 이미지 파일은 사용할 수 없습니다.")
    if len(image_bytes) > MAX_IMAGE_UPLOAD_BYTES:
        raise ImageInputValidationError(
            "이미지 파일이 너무 큽니다. "
            f"최대 {MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)}MB까지 사용할 수 있습니다."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as opened_image:
                image_format = str(opened_image.format or "").upper()
                if image_format not in SUPPORTED_IMAGE_FORMAT_MIME_TYPES:
                    raise ImageInputValidationError(
                        "PNG, JPG/JPEG 또는 WEBP 이미지만 사용할 수 있습니다."
                    )
                if image_format != expected_format:
                    raise ImageInputValidationError(
                        "파일 확장자와 실제 이미지 형식이 일치하지 않습니다."
                    )
                if getattr(opened_image, "is_animated", False):
                    raise ImageInputValidationError(
                        "움직이는 이미지는 지원하지 않습니다. 정지 화면을 사용해주세요."
                    )
                width, height = opened_image.size
                if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                    raise ImageInputValidationError(
                        "이미지가 너무 작습니다. 가로와 세로가 각각 32px 이상이어야 합니다."
                    )
                if width * height > MAX_IMAGE_INPUT_PIXELS:
                    raise ImageInputValidationError(
                        "이미지 해상도가 너무 큽니다. 2,400만 픽셀 이하로 줄여주세요."
                    )
                opened_image.load()
                normalized_image = ImageOps.exif_transpose(opened_image).copy()
    except ImageInputValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ImageInputValidationError(
            "이미지 파일이 손상되었거나 읽을 수 없는 형식입니다."
        ) from error

    if max(normalized_image.size) > AI_IMAGE_MAX_DIMENSION:
        normalized_image.thumbnail(
            (AI_IMAGE_MAX_DIMENSION, AI_IMAGE_MAX_DIMENSION),
            Image.Resampling.LANCZOS,
        )

    prepared_bytes = _save_normalized_image(
        normalized_image,
        image_format,
    )
    if len(prepared_bytes) > MAX_PREPARED_IMAGE_BYTES:
        raise ImageInputValidationError(
            "이미지를 분석용 크기로 준비하지 못했습니다. 해상도를 더 줄여주세요."
        )
    mime_type = SUPPORTED_IMAGE_FORMAT_MIME_TYPES[image_format]
    encoded_image = base64.b64encode(prepared_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded_image}"
    return PreparedImageInput(
        data_url=data_url,
        mime_type=mime_type,
        width=normalized_image.width,
        height=normalized_image.height,
        original_size_bytes=len(image_bytes),
        prepared_size_bytes=len(prepared_bytes),
        sha256=hashlib.sha256(prepared_bytes).hexdigest(),
    )


def prepare_images_for_ai(
    image_uploads: Sequence[tuple[bytes, str, str | None]],
) -> tuple[PreparedImageInput, ...]:
    """여러 이미지를 개수·총용량까지 검증해 첨부 순서대로 준비합니다."""

    if not image_uploads:
        raise ImageInputValidationError("이미지 파일을 한 장 이상 선택해주세요.")
    if len(image_uploads) > MAX_IMAGE_COUNT:
        raise ImageInputValidationError(
            f"이미지는 한 번에 최대 {MAX_IMAGE_COUNT}장까지 사용할 수 있습니다."
        )
    total_upload_size = sum(
        len(image_bytes)
        for image_bytes, _filename, _mime_type in image_uploads
        if isinstance(image_bytes, bytes)
    )
    if total_upload_size > MAX_TOTAL_IMAGE_UPLOAD_BYTES:
        raise ImageInputValidationError(
            "이미지 전체 용량이 너무 큽니다. "
            f"합계 {MAX_TOTAL_IMAGE_UPLOAD_BYTES // (1024 * 1024)}MB 이하로 "
            "줄여주세요."
        )

    prepared_images = tuple(
        prepare_image_for_ai(
            image_bytes=image_bytes,
            filename=filename,
            declared_mime_type=mime_type,
        )
        for image_bytes, filename, mime_type in image_uploads
    )
    if (
        sum(image.prepared_size_bytes for image in prepared_images)
        > MAX_TOTAL_PREPARED_IMAGE_BYTES
    ):
        raise ImageInputValidationError(
            "분석용 이미지 전체 크기가 너무 큽니다. 이미지 수나 해상도를 줄여주세요."
        )
    image_hashes = [image.sha256 for image in prepared_images]
    if len(image_hashes) != len(set(image_hashes)):
        raise ImageInputValidationError(
            "같은 이미지가 두 번 이상 첨부되어 있습니다. 중복 이미지를 제거해주세요."
        )
    return prepared_images


def restore_prepared_image(
    payload: object,
) -> PreparedImageInput | None:
    """세션 payload를 재검증해 AI 입력 이미지로 복원합니다."""

    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ImageInputValidationError("저장된 이미지 세션 정보가 올바르지 않습니다.")
    try:
        restored = PreparedImageInput(**payload)
    except (TypeError, ValueError) as error:
        raise ImageInputValidationError(
            "저장된 이미지 세션 정보가 올바르지 않습니다."
        ) from error
    expected_prefix = f"data:{restored.mime_type};base64,"
    if (
        restored.mime_type not in SUPPORTED_IMAGE_FORMAT_MIME_TYPES.values()
        or not restored.data_url.startswith(expected_prefix)
        or restored.width < 1
        or restored.height < 1
        or restored.original_size_bytes < 1
        or restored.prepared_size_bytes < 1
        or len(restored.sha256) != 64
    ):
        raise ImageInputValidationError(
            "저장된 이미지 세션 정보가 올바르지 않습니다."
        )
    try:
        decoded_image = base64.b64decode(
            restored.data_url[len(expected_prefix) :],
            validate=True,
        )
    except (ValueError, binascii.Error) as error:
        raise ImageInputValidationError(
            "저장된 이미지 세션 정보가 올바르지 않습니다."
        ) from error
    if (
        len(decoded_image) != restored.prepared_size_bytes
        or len(decoded_image) > MAX_PREPARED_IMAGE_BYTES
        or hashlib.sha256(decoded_image).hexdigest() != restored.sha256
    ):
        raise ImageInputValidationError(
            "저장된 이미지 세션 정보가 올바르지 않습니다."
        )
    return restored


def restore_prepared_images(
    payloads: object,
) -> tuple[PreparedImageInput, ...]:
    """세션의 다중 이미지 payload를 개수·총크기와 함께 재검증합니다."""

    if payloads is None:
        return ()
    if not isinstance(payloads, (list, tuple)):
        raise ImageInputValidationError("저장된 이미지 세션 정보가 올바르지 않습니다.")
    if len(payloads) > MAX_IMAGE_COUNT:
        raise ImageInputValidationError("저장된 이미지 개수가 허용 범위를 벗어났습니다.")

    restored_images: list[PreparedImageInput] = []
    for payload in payloads:
        restored_image = restore_prepared_image(payload)
        if restored_image is None:
            raise ImageInputValidationError(
                "저장된 이미지 세션 정보가 올바르지 않습니다."
            )
        restored_images.append(restored_image)
    if (
        sum(image.prepared_size_bytes for image in restored_images)
        > MAX_TOTAL_PREPARED_IMAGE_BYTES
    ):
        raise ImageInputValidationError("저장된 이미지 전체 크기가 허용 범위를 벗어났습니다.")
    if (
        sum(image.original_size_bytes for image in restored_images)
        > MAX_TOTAL_IMAGE_UPLOAD_BYTES
    ):
        raise ImageInputValidationError("저장된 이미지 원본 크기가 허용 범위를 벗어났습니다.")
    image_hashes = [image.sha256 for image in restored_images]
    if len(image_hashes) != len(set(image_hashes)):
        raise ImageInputValidationError("저장된 이미지 세션에 중복 이미지가 있습니다.")
    return tuple(restored_images)


def build_input_image_content(
    image: PreparedImageInput,
) -> dict[str, str]:
    """Responses API의 고해상도 이미지 입력 블록을 만듭니다."""

    return {
        "type": "input_image",
        "image_url": image.data_url,
        "detail": "high",
    }
