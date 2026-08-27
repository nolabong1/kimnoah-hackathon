import io
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_PDF_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DIRECT_SOURCE_TEXT_CHARS = 30_000
MAX_SOURCE_TEXT_CHARS = 90_000
MAX_SOURCE_CHUNK_CHARS = 20_000
MAX_SOURCE_TITLE_CHARS = 200
MIN_MEANINGFUL_PDF_CHARS = 20
MIN_LAYOUT_SCORE_ADVANTAGE = 10
REPEATED_EDGE_LINE_RATIO = 0.6


class SourceMaterialValidationError(ValueError):
    """사용자 원본 자료가 검증 규칙을 만족하지 못했습니다."""


@dataclass(frozen=True)
class PdfExtractionResult:
    """PDF 텍스트와 사용자에게 보여줄 결정론적 추출 진단입니다."""

    text: str
    page_count: int
    extracted_page_count: int
    empty_page_count: int
    layout_page_count: int
    removed_repeated_line_count: int
    warnings: tuple[str, ...] = ()

    def to_summary(self) -> dict:
        """Streamlit 세션에 저장하기 쉬운 요약 객체로 변환합니다."""

        summary = asdict(self)
        summary.pop("text", None)
        return summary


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


def _normalize_pdf_page_text(page_text: str) -> str:
    """페이지 내부 구조를 보존하며 흔한 줄바꿈 깨짐을 정리합니다."""

    normalized_text = normalize_source_text(page_text)
    normalized_text = re.sub(
        r"(?<=[A-Za-z])-\n(?=[A-Za-z])",
        "",
        normalized_text,
    )
    return normalized_text


def _extraction_quality_score(page_text: str) -> int:
    """두 추출 방식 중 더 온전한 결과를 고르는 보수적 점수입니다."""

    if not page_text:
        return 0

    meaningful_count = sum(character.isalnum() for character in page_text)
    replacement_penalty = page_text.count("\ufffd") * 30
    control_penalty = sum(
        10
        for character in page_text
        if ord(character) < 32 and character not in {"\n", "\t"}
    )
    readable_lines = [
        line
        for line in page_text.splitlines()
        if sum(character.isalnum() for character in line) >= 4
    ]
    isolated_line_penalty = sum(
        2
        for line in page_text.splitlines()
        if 0 < sum(character.isalnum() for character in line) <= 1
    )
    structure_bonus = min(len(readable_lines), 10)
    return (
        meaningful_count
        + structure_bonus
        - replacement_penalty
        - control_penalty
        - isolated_line_penalty
    )


def _extract_page_text(page) -> tuple[str, str]:
    """일반·레이아웃 추출을 비교해 페이지별 최선의 결과를 반환합니다."""

    plain_text = _normalize_pdf_page_text(page.extract_text() or "")
    try:
        layout_text = _normalize_pdf_page_text(
            page.extract_text(
                extraction_mode="layout",
                layout_mode_space_vertically=False,
            )
            or ""
        )
    except Exception:
        layout_text = ""
    plain_score = _extraction_quality_score(plain_text)
    layout_score = _extraction_quality_score(layout_text)

    if (
        layout_text
        and layout_text != plain_text
        and layout_score
        >= plain_score + max(
            MIN_LAYOUT_SCORE_ADVANTAGE,
            math.ceil(max(plain_score, 0) * 0.02),
        )
    ):
        return layout_text, "layout"
    return plain_text, "plain"


def _edge_line_key(line: str) -> str:
    """반복 머리말·꼬리말 비교용 문자열을 만듭니다."""

    return " ".join(line.split()).casefold()


def _looks_like_page_number(line: str) -> bool:
    """페이지 가장자리의 단독 페이지 번호 표현을 판정합니다."""

    cleaned_line = " ".join(line.split()).casefold()
    return bool(
        re.fullmatch(
            r"(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?|[-–—]\s*\d+\s*[-–—]",
            cleaned_line,
        )
    )


def _remove_repeated_page_edges(
    page_texts: list[tuple[int, str]],
) -> tuple[list[tuple[int, str]], int]:
    """여러 페이지에 반복되는 가장자리 머리말·꼬리말을 제거합니다."""

    if not page_texts:
        return [], 0

    edge_counts: Counter[str] = Counter()
    for _, page_text in page_texts:
        nonempty_lines = [
            line for line in page_text.splitlines() if line.strip()
        ]
        edge_keys = {
            _edge_line_key(line)
            for line in nonempty_lines[:2] + nonempty_lines[-2:]
            if len(_edge_line_key(line)) >= 3
        }
        edge_counts.update(edge_keys)

    repeated_threshold = max(
        2,
        math.ceil(len(page_texts) * REPEATED_EDGE_LINE_RATIO),
    )
    repeated_keys = {
        line_key
        for line_key, count in edge_counts.items()
        if count >= repeated_threshold
    }
    cleaned_pages: list[tuple[int, str]] = []
    removed_count = 0

    for page_number, page_text in page_texts:
        lines = page_text.splitlines()
        nonempty_indexes = [
            index for index, line in enumerate(lines) if line.strip()
        ]
        edge_indexes = set(
            nonempty_indexes[:2] + nonempty_indexes[-2:]
        )
        kept_lines = []

        for index, line in enumerate(lines):
            should_remove = index in edge_indexes and (
                _edge_line_key(line) in repeated_keys
                or _looks_like_page_number(line)
            )
            if should_remove:
                removed_count += 1
            else:
                kept_lines.append(line)

        cleaned_page = normalize_source_text("\n".join(kept_lines))
        if cleaned_page:
            cleaned_pages.append((page_number, cleaned_page))

    return cleaned_pages, removed_count


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


def _split_oversized_text_block(
    text_block: str,
    max_chars: int,
) -> list[str]:
    """글자를 버리지 않고 가까운 공백에서 큰 텍스트 블록을 나눕니다."""

    remaining_text = text_block.strip()
    split_blocks = []

    while len(remaining_text) > max_chars:
        split_index = remaining_text.rfind(" ", 0, max_chars + 1)
        if split_index < max_chars // 2:
            split_index = max_chars
        split_blocks.append(remaining_text[:split_index].strip())
        remaining_text = remaining_text[split_index:].strip()

    if remaining_text:
        split_blocks.append(remaining_text)
    return split_blocks


def split_source_text(
    source_text: str,
    max_chars: int = MAX_SOURCE_CHUNK_CHARS,
) -> list[str]:
    """페이지·문단 경계를 우선해 긴 원본을 손실 없이 분할합니다."""

    cleaned_text = validate_source_text(source_text)
    if max_chars < 1_000:
        raise ValueError("원본 분할 크기는 1,000자 이상이어야 합니다.")
    if len(cleaned_text) <= max_chars:
        return [cleaned_text]

    raw_blocks = [
        block.strip()
        for block in re.split(r"\n{2,}", cleaned_text)
        if block.strip()
    ]
    content_blocks = []
    current_page_marker = ""

    for raw_block in raw_blocks:
        page_match = re.match(r"^\[페이지 \d+\]\s*", raw_block)
        if page_match:
            current_page_marker = page_match.group(0).strip()
            page_body = raw_block[page_match.end():].strip()
        else:
            page_body = raw_block

        available_chars = max_chars
        if current_page_marker:
            available_chars -= len(current_page_marker) + 1
        for block_part in _split_oversized_text_block(
            page_body,
            available_chars,
        ):
            content_blocks.append(
                (
                    f"{current_page_marker}\n{block_part}"
                    if current_page_marker
                    else block_part
                )
            )

    chunks = []
    current_chunk = ""
    for content_block in content_blocks:
        candidate = (
            f"{current_chunk}\n\n{content_block}"
            if current_chunk
            else content_block
        )
        if len(candidate) <= max_chars:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = content_block

    if current_chunk:
        chunks.append(current_chunk)
    if not chunks or any(len(chunk) > max_chars for chunk in chunks):
        raise RuntimeError("원본을 안전한 길이로 분할하지 못했습니다.")
    return chunks


def inspect_pdf_upload(
    pdf_bytes: bytes,
    filename: str,
) -> int:
    """AI 정밀 읽기 전에 PDF 형식·크기·암호화와 페이지 수를 검사합니다."""

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
        page_count = len(reader.pages)
    except SourceMaterialValidationError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise SourceMaterialValidationError(
            "올바른 PDF 파일인지 확인해주세요."
        ) from error

    if page_count < 1:
        raise SourceMaterialValidationError(
            "페이지가 없는 PDF는 사용할 수 없습니다."
        )
    return page_count


def extract_pdf_document(
    pdf_bytes: bytes,
    filename: str,
) -> PdfExtractionResult:
    """PDF를 메모리에서 읽고 페이지 인식 텍스트와 품질 진단을 만듭니다."""

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

        page_count = len(reader.pages)
        page_texts: list[tuple[int, str]] = []
        layout_page_count = 0

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text, extraction_mode = _extract_page_text(page)
            except Exception as error:
                raise SourceMaterialValidationError(
                    f"PDF {page_number}페이지의 텍스트를 읽지 못했습니다."
                ) from error

            if page_text:
                page_texts.append((page_number, page_text))
                if extraction_mode == "layout":
                    layout_page_count += 1
    except SourceMaterialValidationError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise SourceMaterialValidationError(
            "올바른 PDF 파일인지 확인해주세요."
        ) from error

    cleaned_pages, removed_line_count = _remove_repeated_page_edges(
        page_texts
    )
    page_sections = [
        f"[페이지 {page_number}]\n{page_text}"
        for page_number, page_text in cleaned_pages
    ]
    extracted_text = normalize_source_text("\n\n".join(page_sections))
    meaningful_char_count = sum(
        character.isalnum() for character in extracted_text
    )
    if meaningful_char_count < MIN_MEANINGFUL_PDF_CHARS:
        raise SourceMaterialValidationError(
            "PDF에서 의미 있는 텍스트를 추출하지 못했습니다. "
            "스캔본이나 이미지 전용 PDF는 현재 지원하지 않습니다."
        )

    cleaned_text = validate_source_text(extracted_text)
    extracted_page_count = len(cleaned_pages)
    empty_page_count = max(page_count - extracted_page_count, 0)
    warnings = []
    if empty_page_count:
        warnings.append(
            f"텍스트가 없는 {empty_page_count}개 페이지는 제외했습니다."
        )
    if layout_page_count:
        warnings.append(
            f"{layout_page_count}개 페이지는 레이아웃 보존 추출을 사용했습니다."
        )
    if removed_line_count:
        warnings.append(
            f"반복 머리말·꼬리말 또는 페이지 번호 {removed_line_count}줄을 "
            "정리했습니다."
        )
    if "\ufffd" in cleaned_text:
        warnings.append(
            "일부 글자가 깨져 있을 수 있어 생성 결과의 원문 근거를 "
            "확인해주세요."
        )

    return PdfExtractionResult(
        text=cleaned_text,
        page_count=page_count,
        extracted_page_count=extracted_page_count,
        empty_page_count=empty_page_count,
        layout_page_count=layout_page_count,
        removed_repeated_line_count=removed_line_count,
        warnings=tuple(warnings),
    )


def extract_pdf_text(
    pdf_bytes: bytes,
    filename: str,
) -> str:
    """기존 호출자와 호환되게 PDF 추출 텍스트만 반환합니다."""

    return extract_pdf_document(
        pdf_bytes=pdf_bytes,
        filename=filename,
    ).text
