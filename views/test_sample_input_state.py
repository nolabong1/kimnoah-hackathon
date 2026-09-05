from collections.abc import MutableMapping
from datetime import date
from typing import Any

from views.create_plan_view import (
    COURSE_NAME_INPUT_KEY,
    CURRENT_LEVEL_INPUT_KEY,
    START_DATE_INPUT_KEY,
    STUDY_GOAL_INPUT_KEY,
    get_available_minutes_input_key,
)
from views.source_review_material_view import (
    FINGERPRINT_STATE_KEY,
    RESULT_STATE_KEY,
    SOURCE_TYPE_KEY,
    TEXT_KEY,
    TITLE_KEY,
    VIEW_MODE_KEY,
)
from views.tutor_state import clear_tutor_state
from views.tutor_view import SETUP_ATTEMPT_KEY, SETUP_QUESTION_KEY
from views.weekly_review_state import SAMPLE_REFLECTION_PENDING_KEY


SAMPLE_PLAN = "plan"
SAMPLE_SOURCE_REVIEW = "source_review"
SAMPLE_TUTOR = "tutor"
SAMPLE_WEEKLY_REFLECTION = "weekly_reflection"
SAMPLE_INPUT_OPTIONS = (
    SAMPLE_PLAN,
    SAMPLE_SOURCE_REVIEW,
    SAMPLE_TUTOR,
    SAMPLE_WEEKLY_REFLECTION,
)
SAMPLE_INPUT_LABELS = {
    SAMPLE_PLAN: "AI 학습계획",
    SAMPLE_SOURCE_REVIEW: "텍스트 AI 복습자료",
    SAMPLE_TUTOR: "단계별 힌트 AI 튜터",
    SAMPLE_WEEKLY_REFLECTION: "주간 학습 회고",
}

SAMPLE_SOURCE_TEXT = """파이썬의 조건문은 조건의 참과 거짓에 따라 실행할 코드를 선택한다. if 문은 가장 먼저 검사할 조건을 나타내고, elif 문은 앞선 조건이 거짓일 때 추가 조건을 검사한다. else 문은 앞의 모든 조건이 거짓일 때 실행된다.

반복문은 같은 작업을 여러 번 수행할 때 사용한다. for 문은 문자열이나 리스트처럼 순서가 있는 값에서 항목을 하나씩 꺼내 처리할 때 적합하다. while 문은 주어진 조건이 참인 동안 반복하므로, 반복 안에서 조건이 언젠가 거짓이 되도록 값을 바꾸어야 한다. 그렇지 않으면 반복이 끝나지 않을 수 있다.

조건문과 반복문을 함께 사용하면 여러 데이터 중 원하는 값만 골라 처리할 수 있다. 예를 들어 숫자 목록을 for 문으로 순회하면서 if 문으로 짝수인지 확인하면 짝수만 출력할 수 있다. 코드를 작성한 뒤에는 조건의 경계값, 반복 횟수, 종료 조건을 확인하는 것이 중요하다."""

SAMPLE_REFLECTION_ANSWERS = {
    "went_well": (
        "매일 해야 할 과제를 확인하고, 학습자료를 본 뒤 퀴즈로 이해도를 "
        "점검한 점이 잘되었습니다."
    ),
    "difficulty": (
        "응용 문제에서 조건을 코드로 옮기는 과정이 어려웠고 복습 과제 일부가 "
        "예정보다 늦어졌습니다."
    ),
    "effective_method": (
        "짧게 개념을 읽고 예제를 직접 작성한 다음 틀린 이유를 확인하는 방식이 "
        "효과적이었습니다."
    ),
    "improvement_intention": (
        "다음 주에는 어려운 개념을 학습 초반에 다시 보고, 매일 마지막 10분을 "
        "오답 복습에 사용하고 싶습니다."
    ),
}


def apply_sample_input(
    state: MutableMapping[str, Any],
    sample_type: str,
    today: date,
) -> tuple[str, str]:
    """선택 기능의 샘플 입력만 적용하고 이동할 화면과 안내를 반환합니다."""

    if sample_type == SAMPLE_PLAN:
        for key in (
            "generated_plan",
            "generated_plan_start_date",
            "generated_plan_metadata",
            "generated_plan_saved",
            "saved_plan_id",
        ):
            state.pop(key, None)
        state.update(
            {
                COURSE_NAME_INPUT_KEY: "파이썬 기초",
                STUDY_GOAL_INPUT_KEY: (
                    "조건문과 반복문을 활용해 간단한 콘솔 프로그램을 만들고 "
                    "코드의 실행 흐름을 설명할 수 있다."
                ),
                CURRENT_LEVEL_INPUT_KEY: 3,
                START_DATE_INPUT_KEY: today,
            }
        )
        for day_offset, minutes in enumerate((50, 50, 40, 60, 40, 60, 45)):
            state[get_available_minutes_input_key(day_offset)] = minutes
        return "계획 만들기", "AI 학습계획 샘플 입력을 채웠습니다."

    if sample_type == SAMPLE_SOURCE_REVIEW:
        state.pop(RESULT_STATE_KEY, None)
        state.pop(FINGERPRINT_STATE_KEY, None)
        state.update(
            {
                VIEW_MODE_KEY: "create",
                SOURCE_TYPE_KEY: "text",
                TITLE_KEY: "파이썬 조건문과 반복문 핵심 정리",
                TEXT_KEY: SAMPLE_SOURCE_TEXT,
            }
        )
        return (
            "AI 복습 자료 만들기",
            "텍스트 AI 복습자료 샘플 입력을 채웠습니다.",
        )

    if sample_type == SAMPLE_TUTOR:
        clear_tutor_state(state)
        state.update(
            {
                SETUP_QUESTION_KEY: (
                    "어떤 수 x에 3을 더한 뒤 그 결과를 2배했더니 18이 "
                    "되었습니다. x의 값을 구하고 풀이 과정을 설명해주세요."
                ),
                SETUP_ATTEMPT_KEY: (
                    "18에서 먼저 3을 빼고 2로 나누어 x가 7.5라고 "
                    "생각했습니다."
                ),
            }
        )
        return "단계별 힌트 AI 튜터", "AI 튜터 샘플 입력을 채웠습니다."

    if sample_type == SAMPLE_WEEKLY_REFLECTION:
        state[SAMPLE_REFLECTION_PENDING_KEY] = dict(
            SAMPLE_REFLECTION_ANSWERS
        )
        return "주간 학습 회고", "주간 회고 샘플 답변을 준비했습니다."

    raise ValueError("지원하지 않는 샘플 입력 유형입니다.")
