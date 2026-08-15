import json

from models.review_material import ReviewMaterialDraft
from services.openai_client import (
    get_openai_client,
    get_openai_model,
)


SYSTEM_PROMPT = """
당신은 대학생의 자기주도학습을 돕는 전문 학습 코치입니다.

사용자에게 주어진 과제 정보를 바탕으로 정확하고 이해하기 쉬운
한국어 학습자료를 작성하세요.

다음 원칙을 반드시 지키세요.

- 사용자의 과목, 학습 목표, 현재 수준을 반영합니다.
- current_level은 1부터 10까지이며 숫자가 클수록 숙련도가 높습니다.
- task_type이 learn이면 새로운 개념을 이해하도록 설명합니다.
- task_type이 review이면 이미 학습한 내용을 회상하고 정리하도록 돕습니다.
- estimated_minutes 안에 읽고 학습할 수 있는 현실적인 분량으로 작성합니다.
- 원본 학습자료를 받지 않았으므로 특정 교재나 자료를 봤다고 주장하지 않습니다.
- 제공되지 않은 시험 범위, 교재 내용, 수업 내용을 임의로 만들어내지 않습니다.
- 과제의 정보가 제한적이라면 검증된 일반 개념과 기초 내용을 중심으로 설명합니다.
- title은 200자 이하의 간결한 제목으로 작성합니다.
- content_markdown에는 제목을 다시 넣지 않습니다.
- content_markdown은 반드시 아래 5개 섹션을 같은 순서로 포함합니다.

## 핵심 요약
## 주요 개념
## 상세 설명
## 학습 예시
## 스스로 확인하기

- 주요 개념은 목록을 활용해 읽기 쉽게 정리합니다.
- 상세 설명은 현재 수준에 맞춰 단계적으로 작성합니다.
- 학습 예시에는 개념을 적용한 구체적인 사례를 포함합니다.
- 스스로 확인하기에는 짧은 확인 질문과 정답 및 해설을 포함합니다.
- Markdown 문법을 사용하되 지나치게 복잡한 표는 피합니다.
"""


REQUIRED_SECTIONS = (
    "## 핵심 요약",
    "## 주요 개념",
    "## 상세 설명",
    "## 학습 예시",
    "## 스스로 확인하기",
)


def _is_valid_review_material(
    material: ReviewMaterialDraft,
) -> bool:
    """필수 Markdown 섹션과 기본 내용을 검사합니다."""

    if not material.title.strip():
        return False

    if len(material.title) > 200:
        return False

    if not material.content_markdown.strip():
        return False

    return all(
        section in material.content_markdown
        for section in REQUIRED_SECTIONS
    )


def generate_review_material(
    course_name: str,
    goal: str,
    current_level: int,
    task_title: str,
    task_description: str,
    task_type: str,
    estimated_minutes: int,
) -> ReviewMaterialDraft:
    """과제 정보를 기반으로 AI 학습·복습 자료를 생성합니다."""

    if task_type not in {"learn", "review"}:
        raise ValueError(
            "학습자료는 learn 또는 review 과제에서만 생성할 수 있습니다."
        )

    client = get_openai_client()

    user_input = {
        "course_name": course_name,
        "goal": goal,
        "current_level": current_level,
        "task": {
            "title": task_title,
            "description": task_description,
            "task_type": task_type,
            "estimated_minutes": estimated_minutes,
        },
    }

    for attempt in range(2):
        correction = ""

        if attempt == 1:
            correction = """
            이전 결과가 필수 Markdown 섹션을 누락했습니다.
            content_markdown에는 다음 섹션을 정확히 한 번씩,
            지정된 순서대로 포함하세요.

            ## 핵심 요약
            ## 주요 개념
            ## 상세 설명
            ## 학습 예시
            ## 스스로 확인하기
            """

        response = client.responses.parse(
            model=get_openai_model(),
            reasoning={
                "effort": "low",
            },
            input=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT + correction,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        user_input,
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=ReviewMaterialDraft,
        )

        material = response.output_parsed

        if (
            material is not None
            and _is_valid_review_material(material)
        ):
            return material

    raise RuntimeError(
        "AI가 필수 구성에 맞는 학습자료를 생성하지 못했습니다."
    )
