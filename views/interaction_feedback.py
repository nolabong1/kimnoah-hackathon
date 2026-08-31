from hashlib import sha256
import streamlit as st

from services.gamification_catalog import (
    ACHIEVEMENTS_BY_KEY,
    CHALLENGE_TEMPLATES_BY_KEY,
)
from views.interaction_feedback_component import (
    render_interaction_feedback_component,
)
from views.interaction_state import (
    defer_completion_interaction_events,
    normalize_interaction_event,
    pop_interaction_events,
)


def _build_gamification_events(notifications: object) -> list[dict]:
    """기존 게임화 알림을 안전한 공통 연출 이벤트로 변환합니다."""

    if not isinstance(notifications, list):
        return []
    events = []
    for notification in notifications:
        if not isinstance(notification, dict):
            continue
        achievement_key = notification.get("achievement_key")
        if isinstance(achievement_key, str):
            definition = ACHIEVEMENTS_BY_KEY.get(achievement_key)
            reward_exp = notification.get("reward_exp")
            if definition is None or not isinstance(reward_exp, int):
                continue
            event = normalize_interaction_event(
                {
                    "event_id": f"achievement_unlock:{achievement_key}",
                    "kind": "achievement_unlock",
                    "tone": "achievement",
                    "title": f"업적 해금 · {definition.name_ko}",
                    "message": definition.description_ko,
                    "value": f"+{reward_exp} EXP",
                    "icon": definition.badge.icon,
                }
            )
            if event is not None:
                events.append(event)
            continue

        challenge_id = notification.get("challenge_id")
        template_key = notification.get("template_key")
        if not isinstance(challenge_id, str) or not isinstance(template_key, str):
            continue
        template = CHALLENGE_TEMPLATES_BY_KEY.get(template_key)
        if template is None:
            continue
        event = normalize_interaction_event(
            {
                "event_id": f"challenge_complete:{challenge_id}",
                "kind": "challenge_complete",
                "tone": "challenge",
                "title": f"도전과제 완료 · {template.name_ko}",
                "message": "업적·도전과제에서 보상을 직접 수령할 수 있습니다.",
                "value": "보상 수령 가능",
                "icon": "◎",
            }
        )
        if event is not None:
            events.append(event)
    return events


def render_interaction_event_batch(
    events: object,
    *,
    placement: str = "overlay",
) -> None:
    """검증된 이벤트 묶음을 지정한 위치에서 한 번 재생합니다."""

    if not isinstance(events, list):
        return
    normalized_events = [
        normalized
        for event in events
        if (normalized := normalize_interaction_event(event)) is not None
    ]
    if not normalized_events:
        return
    event_signature = "|".join(
        event["event_id"] for event in normalized_events
    )
    normalized_placement = "inline" if placement == "inline" else "overlay"
    batch_source = f"{normalized_placement}|{event_signature}"
    batch_id = sha256(batch_source.encode("utf-8")).hexdigest()[:16]
    render_interaction_feedback_component(
        normalized_events,
        key=f"interaction_feedback_batch_{batch_id}",
        placement=normalized_placement,
    )


def render_interaction_feedback(
    gamification_notifications: object = None,
) -> None:
    """이번 rerun의 학습·게임화 결과를 한 번 표시하거나 dialog로 넘깁니다."""

    events = pop_interaction_events(st.session_state)
    events.extend(_build_gamification_events(gamification_notifications))
    if not events:
        return
    if isinstance(st.session_state.get("task_completion_feedback"), dict):
        defer_completion_interaction_events(st.session_state, events)
        return
    render_interaction_event_batch(events)
