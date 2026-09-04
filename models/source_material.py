from pydantic import BaseModel, Field, field_validator, model_validator


class VisualPdfPage(BaseModel):
    """AI가 한 PDF 페이지에서 읽은 텍스트와 시각 정보입니다."""

    page_number: int = Field(ge=1)
    content_text: str = Field(
        min_length=1,
        description="페이지에서 읽은 텍스트를 순서대로 충실하게 옮긴 내용",
    )
    visual_notes: list[str] = Field(
        max_length=8,
        description="학습에 필요한 표, 도표, 수식 또는 그림의 관찰 가능한 설명",
    )

    @field_validator("content_text")
    @classmethod
    def strip_content_text(cls, value: str) -> str:
        """페이지 텍스트의 앞뒤 공백을 제거합니다."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("PDF 페이지 텍스트는 비어 있을 수 없습니다.")
        return cleaned_value

    @field_validator("visual_notes")
    @classmethod
    def strip_visual_notes(cls, values: list[str]) -> list[str]:
        """시각 정보 목록에서 빈 항목을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("PDF 시각 정보에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values


class VisualPdfExtraction(BaseModel):
    """PDF 파일 입력을 통해 AI가 복원한 페이지별 학습 원본입니다."""

    pages: list[VisualPdfPage] = Field(min_length=1, max_length=20)
    extraction_warnings: list[str] = Field(
        max_length=10,
        description="읽기 어렵거나 불확실했던 부분에 대한 짧은 경고",
    )

    @field_validator("extraction_warnings")
    @classmethod
    def strip_warnings(cls, values: list[str]) -> list[str]:
        """추출 경고의 공백을 정리합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("PDF 추출 경고에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values

    @model_validator(mode="after")
    def validate_page_order(self) -> "VisualPdfExtraction":
        """페이지 번호가 중복 없이 오름차순인지 확인합니다."""

        page_numbers = [page.page_number for page in self.pages]
        if page_numbers != sorted(set(page_numbers)):
            raise ValueError("PDF 페이지 번호는 중복 없이 오름차순이어야 합니다.")
        return self


class VisualImageExtraction(BaseModel):
    """순서가 지정된 학습 이미지 한 장의 판독 결과입니다."""

    image_number: int = Field(
        ge=1,
        le=8,
        description="사용자가 첨부한 순서 기준 이미지 번호",
    )

    content_text: str = Field(
        max_length=30_000,
        description=(
            "이미지에서 읽은 글자와 수식을 읽기 순서대로 옮긴 내용. "
            "읽을 글자가 없으면 빈 문자열"
        ),
    )
    visual_notes: list[str] = Field(
        max_length=12,
        description="표, 도표, 그래프 또는 그림에서 직접 관찰되는 학습 정보",
    )
    extraction_warnings: list[str] = Field(
        max_length=10,
        description="가려짐, 흐림 등 판독이 불확실한 부분에 대한 짧은 경고",
    )

    @field_validator("content_text")
    @classmethod
    def strip_image_content_text(cls, value: str) -> str:
        """이미지 판독 텍스트의 앞뒤 공백을 제거합니다."""

        cleaned_value = value.strip()
        return cleaned_value

    @field_validator("visual_notes", "extraction_warnings")
    @classmethod
    def strip_image_lists(cls, values: list[str]) -> list[str]:
        """이미지 분석 목록에서 빈 항목을 거부합니다."""

        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("이미지 분석 목록에 빈 항목을 넣을 수 없습니다.")
        return cleaned_values


class VisualImageBatchExtraction(BaseModel):
    """최대 여덟 장의 학습 이미지를 순서대로 읽은 결과입니다."""

    images: list[VisualImageExtraction] = Field(
        min_length=1,
        max_length=8,
        description="첨부 순서와 같은 순서의 이미지별 판독 결과",
    )

    @model_validator(mode="after")
    def validate_image_order(self) -> "VisualImageBatchExtraction":
        """이미지 번호가 1부터 중복 없이 이어지는지 확인합니다."""

        image_numbers = [image.image_number for image in self.images]
        if image_numbers != list(range(1, len(self.images) + 1)):
            raise ValueError("이미지 번호는 1부터 순서대로 이어져야 합니다.")
        return self
