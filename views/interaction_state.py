from collections.abc import MutableMapping
from typing import Any


INTERACTION_STATE_PREFIX = "interaction_"
INTERACTION_QUEUE_KEY = "interaction_event_queue"
INTERACTION_SEEN_KEY = "interaction_seen_event_ids"
INTERACTION_COMPLETION_EVENTS_KEY = "interaction_completion_dialog_events"
MAX_QUEUED_EVENTS = 12
MAX_SEEN_EVENTS = 100
ALLOWED_EVENT_KINDS = {
    "task_complete",
    "daily_bonus",
    "quiz_result",
    "achievement_unlock",
    "challenge_complete",
}
ALLOWED_EVENT_TONES = {
    "success",
    "bonus",
    "quiz",
    "achievement",
    "challenge",
}


def clear_interaction_state(state: MutableMapping[str, Any]) -> None:
    """인터랙션 전용 상태만 제거해 다른 화면 상태를 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(INTERACTION_STATE_PREFIX):
            state.pop(key, None)


def _normalize_text(
    value: object,
    *,
    maximum: int,
) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        return None
    return normalized


def normalize_interaction_event(event: object) -> dict | None:
    """컴포넌트에 전달할 일회성 이벤트를 제한된 형식으로 검증합니다."""

    if not isinstance(event, dict):
        return None
    event_id = _normalize_text(event.get("event_id"), maximum=200)
    kind = _normalize_text(event.get("kind"), maximum=40)
    tone = _normalize_text(event.get("tone"), maximum=40)
    title = _normalize_text(event.get("title"), maximum=100)
    message = _normalize_text(event.get("message"), maximum=240)
    value = _normalize_text(event.get("value"), maximum=60)
    icon = _normalize_text(event.get("icon"), maximum=20)
    if (
        event_id is None
        or kind not in ALLOWED_EVENT_KINDS
        or tone not in ALLOWED_EVENT_TONES
        or title is None
        or message is None
        or value is None
        or icon is None
    ):
        return None
    return {
        "event_id": event_id,
        "kind": kind,
        "tone": tone,
        "title": title,
        "message": message,
        "value": value,
        "icon": icon,
    }


def queue_interaction_event(
    state: MutableMapping[str, Any],
    event: object,
) -> bool:
    """유효하고 아직 보지 않은 이벤트만 제한된 큐에 추가합니다."""

    normalized = normalize_interaction_event(event)
    if normalized is None:
        return False

    raw_seen = state.get(INTERACTION_SEEN_KEY, [])
    seen = list(raw_seen) if isinstance(raw_seen, list) else []
    raw_queue = state.get(INTERACTION_QUEUE_KEY, [])
    queue = list(raw_queue) if isinstance(raw_queue, list) else []
    known_ids = {
        item.get("event_id")
        for item in queue
        if isinstance(item, dict)
    }
    if normalized["event_id"] in seen or normalized["event_id"] in known_ids:
        return False

    queue.append(normalized)
    state[INTERACTION_QUEUE_KEY] = queue[-MAX_QUEUED_EVENTS:]
    return True


def queue_task_completion_interactions(
    state: MutableMapping[str, Any],
    *,
    task_id: object,
    result: object,
) -> None:
    """서버가 새로 완료했다고 확정한 과제 보상만 연출 큐에 넣습니다."""

    if not isinstance(result, dict) or result.get("already_completed") is not False:
        return
    normalized_task_id = _normalize_text(task_id, maximum=100)
    task_exp = result.get("task_exp")
    daily_bonus_exp = result.get("daily_bonus_exp")
    total_exp = result.get("total_exp")
    if (
        normalized_task_id is None
        or isinstance(task_exp, bool)
        or not isinstance(task_exp, int)
        or task_exp <= 0
        or isinstance(total_exp, bool)
        or not isinstance(total_exp, int)
        or total_exp < 0
    ):
        return

    queue_interaction_event(
        state,
        {
            "event_id": f"task_complete:{normalized_task_id}",
            "kind": "task_complete",
            "tone": "success",
            "title": "과제 완료!",
            "message": f"학습 기록이 저장되었습니다 · 총 EXP {total_exp}",
            "value": f"+{task_exp} EXP",
            "icon": "✓",
        },
    )
    if (
        not isinstance(daily_bonus_exp, bool)
        and isinstance(daily_bonus_exp, int)
        and daily_bonus_exp > 0
    ):
        queue_interaction_event(
            state,
            {
                "event_id": f"daily_bonus:{normalized_task_id}",
                "kind": "daily_bonus",
                "tone": "bonus",
                "title": "오늘 학습 완료!",
                "message": "오늘 예정된 과제를 모두 마쳤습니다.",
                "value": f"+{daily_bonus_exp} EXP",
                "icon": "★",
            },
        )


def queue_quiz_result_interaction(
    state: MutableMapping[str, Any],
    attempt: object,
) -> None:
    """저장된 퀴즈 응시 ID와 점수로 결과 연출을 한 번만 예약합니다."""

    if not isinstance(attempt, dict):
        return
    attempt_id = _normalize_text(attempt.get("attempt_id"), maximum=100)
    score = attempt.get("score")
    if (
        attempt_id is None
        or isinstance(score, bool)
        or not isinstance(score, int)
        or not 0 <= score <= 100
    ):
        return
    perfect = score == 100
    queue_interaction_event(
        state,
        {
            "event_id": f"quiz_result:{attempt_id}",
            "kind": "quiz_result",
            "tone": "bonus" if perfect else "quiz",
            "title": "퀴즈 만점!" if perfect else "퀴즈 채점 완료",
            "message": (
                "모든 문항을 맞혔습니다."
                if perfect
                else "결과에서 정오답과 학습 진단을 확인해보세요."
            ),
            "value": f"{score}점",
            "icon": "◆" if perfect else "?",
        },
    )


def pop_interaction_events(
    state: MutableMapping[str, Any],
) -> list[dict]:
    """이번 rerun에 표시할 이벤트를 꺼내고 재생 완료 ID를 기억합니다."""

    raw_events = state.pop(INTERACTION_QUEUE_KEY, [])
    events = []
    if isinstance(raw_events, list):
        events = [
            normalized
            for item in raw_events
            if (normalized := normalize_interaction_event(item)) is not None
        ]
    if not events:
        return []

    raw_seen = state.get(INTERACTION_SEEN_KEY, [])
    seen = list(raw_seen) if isinstance(raw_seen, list) else []
    for event in events:
        event_id = event["event_id"]
        if event_id not in seen:
            seen.append(event_id)
    state[INTERACTION_SEEN_KEY] = seen[-MAX_SEEN_EVENTS:]
    return events


def defer_completion_interaction_events(
    state: MutableMapping[str, Any],
    events: object,
) -> None:
    """과제 완료와 함께 표시할 이벤트를 완료 dialog용으로 보관합니다."""

    if not isinstance(events, list):
        return
    normalized_events = [
        normalized
        for event in events
        if (normalized := normalize_interaction_event(event)) is not None
    ]
    if normalized_events:
        state[INTERACTION_COMPLETION_EVENTS_KEY] = normalized_events[
            -MAX_QUEUED_EVENTS:
        ]


def pop_completion_interaction_events(
    state: MutableMapping[str, Any],
) -> list[dict]:
    """완료 dialog 안에서 한 번 표시할 연출 이벤트를 꺼냅니다."""

    raw_events = state.pop(INTERACTION_COMPLETION_EVENTS_KEY, [])
    if not isinstance(raw_events, list):
        return []
    return [
        normalized
        for event in raw_events
        if (normalized := normalize_interaction_event(event)) is not None
    ]
