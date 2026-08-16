import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_PDF_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SOURCE_TEXT_CHARS = 30_000
MAX_SOURCE_TITLE_CHARS = 200
MIN_MEANINGFUL_PDF_CHARS = 20


class SourceMaterialValidationError(ValueError):
    """사용자 원본 자료가 MVP 검증 규칙을 만족하지 못했습니다."""


def validate_source_title(title: str) -> str:
    """원본 제목을 정리하고 1~200자 범위를 검증합니다."""

    if not isinstance(title, str):
        raise SourceMaterialValidationError("원본 제목을 입력해주세요.")

    cleaned_title = title.strip()
    if not cleaned_title:
        raise SourceMaterialValidationError("원본 제목을 입력해주세요.")
    if len(cleaned_title) > MAX_SOURCE_TITLE_CHARS:
        raise SourceMaterialValidationError(
            f"원본 제목은 {MAX_SOURCE_TITLE_CHARS}자 이하로 입력해주세요."
        )
    return cleaned_title


def normalize_source_text(source_text: str) -> str:
    """문단 구조를 유지하며 과도한 공백과 빈 줄을 정리합니다."""

    normalized_newlines = source_text.replace("\r\n", "\n").replace(
        "\r",
        "\n",
    )
    normalized_lines = [
        re.sub(r"[\t\f\v ]+", " ", line).strip()
        for line in normalized_newlines.split("\n")
    ]
    normalized_text = "\n".join(normalized_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized_text)


def validate_source_text(source_text: str) -> str:
    """원본 텍스트가 비어 있지 않고 비용 제한 이내인지 검사합니다."""

    if not isinstance(source_text, str):
        raise SourceMaterialValidationError("원본 텍스트를 입력해주세요.")

    cleaned_text = normalize_source_text(source_text)
    if not cleaned_text:
        raise SourceMaterialValidationError("원본 텍스트를 입력해주세요.")
    if len(cleaned_text) > MAX_SOURCE_TEXT_CHARS:
        raise SourceMaterialValidationError(
            "원본 내용이 너무 깁니다. "
            f"최대 {MAX_SOURCE_TEXT_CHARS:,}자까지 사용할 수 있으니 "
            "중요한 부분만 남겨 다시 시도해주세요."
        )
    return cleaned_text


def extract_pdf_text(
    pdf_bytes: bytes,
    filename: str,
) -> str:
    """PDF 바이트를 메모리에서 읽어 페이지별 텍스트를 추출합니다."""

    if not filename.lower().endswith(".pdf"):
        raise SourceMaterialValidationError("PDF 파일만 업로드할 수 있습니다.")
    if not pdf_bytes:
        raise SourceMaterialValidationError("빈 PDF 파일은 사용할 수 없습니다.")
    if len(pdf_bytes) > MAX_PDF_UPLOAD_BYTES:
        raise SourceMaterialValidationError(
            "PDF 파일이 너무 큽니다. 최대 10MB까지 업로드할 수 있습니다."
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            raise SourceMaterialValidationError(
                "암호로 보호된 PDF는 현재 지원하지 않습니다."
            )

        page_texts = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = normalize_source_text(page.extract_text() or "")
            except Exception as error:
                raise SourceMaterialValidationError(
                    f"PDF {page_number}페이지의 텍스트를 읽지 못했습니다."
                ) from error

            if page_text:
                page_texts.append(page_text)
    except SourceMaterialValidationError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise SourceMaterialValidationError(
            "올바른 PDF 파일인지 확인해주세요."
        ) from error

    extracted_text = normalize_source_text("\n\n".join(page_texts))
    meaningful_char_count = sum(
        character.isalnum() for character in extracted_text
    )
    if meaningful_char_count < MIN_MEANINGFUL_PDF_CHARS:
        raise SourceMaterialValidationError(
            "PDF에서 의미 있는 텍스트를 추출하지 못했습니다. "
            "스캔본이나 이미지 전용 PDF는 현재 지원하지 않습니다."
        )

    return validate_source_text(extracted_text)
