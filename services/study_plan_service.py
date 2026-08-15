import json

from models.study_plan import WeeklyStudyPlan
from services.openai_client import get_openai_client, get_openai_model


SYSTEM_PROMPT = """
당신은 대학생의 자기주도학습을 돕는 전문 학습 코치입니다.

다음 원칙에 따라 7일 학습계획을 작성하세요.

- day_offset은 0부터 6까지 각각 한 번씩 사용합니다.
- current_level은 사용자가 자기평가한 1부터 10까지의 수준입니다.
- 1은 처음 배우는 단계이고, 10은 설명하고 확장할 수 있는 단계입니다.
- 사용자가 각 요일에 사용할 수 있는 시간을 초과하지 않습니다.
- 과제는 사용자가 바로 실행할 수 있을 정도로 구체적으로 작성합니다.
- description에는 학습 방법과 명확한 완료 기준을 포함합니다.
- learn, review, quiz 과제를 적절히 배치합니다.
- 복습과 퀴즈를 뒤쪽 날짜에 다시 배치하여 기억을 강화합니다.
- 계획이 지나치게 빡빡하지 않도록 현실적인 분량으로 구성합니다.
- course_name은 사용자가 입력한 과목명을 그대로 사용합니다.
"""
def _is_valid_plan(
    plan: WeeklyStudyPlan,
    available_schedule: dict[str, int],
) -> bool:
    """7일 구성과 일일 시간 제한을 검사합니다."""

    day_offsets = [day.day_offset for day in plan.days]

    if day_offsets != list(range(7)):
        return False

    for day in plan.days:
        schedule_key = f"{day.day_offset}일차"
        allowed_minutes = available_schedule.get(schedule_key)

        if allowed_minutes is None:
            return False

        total_minutes = sum(
            task.estimated_minutes for task in day.tasks
        )

        if total_minutes > allowed_minutes:
            return False

        if any(
            task.estimated_minutes < 1
            or task.estimated_minutes > 1440
            for task in day.tasks
        ):
            return False

    return True

def generate_weekly_study_plan(
    course_name: str,
    goal: str,
    current_level: int,
    available_schedule: dict[str, int],
) -> WeeklyStudyPlan:
    """사용자 정보를 반영한 7일 학습계획을 생성합니다."""

    if not 1 <= current_level <= 10:
        raise ValueError(
            "현재 수준은 1부터 10 사이여야 합니다."
        )

    client = get_openai_client()

    user_input = {
        "course_name": course_name,
        "goal": goal,
        "current_level": current_level,
        "available_schedule_minutes": available_schedule,
    }

    for attempt in range(2):
        correction = ""

        if attempt == 1:
            correction = """
            이전 결과가 날짜 중복 또는 일일 시간 제한을 위반했습니다.
            days는 반드시 정확히 7개이며,
            day_offset은 0, 1, 2, 3, 4, 5, 6을 한 번씩만 사용하세요.
            """

        response = client.responses.parse(
            model=get_openai_model(),
            reasoning={"effort": "low"},
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
            text_format=WeeklyStudyPlan,
        )

        plan = response.output_parsed

        if plan is not None and _is_valid_plan(
            plan,
            available_schedule,
        ):
            return plan

    raise RuntimeError(
        "AI가 7일 규칙과 시간 제한에 맞는 계획을 생성하지 못했습니다."
    )
