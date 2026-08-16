from collections.abc import MutableMapping
from typing import Any


GAMIFICATION_STATE_PREFIX = "gamification_"
NOTIFICATION_QUEUE_KEY = "gamification_notification_queue"
SUCCESS_MESSAGE_KEY = "gamification_success_message"
SYNC_IN_PROGRESS_KEY = "gamification_sync_in_progress"
CLAIM_IN_PROGRESS_KEY = "gamification_claim_in_progress"
BADGE_IN_PROGRESS_KEY = "gamification_badge_in_progress"
PENDING_NAVIGATION_KEY = "gamification_pending_navigation"


def clear_gamification_state(state: MutableMapping[str, Any]) -> None:
    """게임화 접두사 상태만 제거해 다른 화면과 인증 상태를 보존합니다."""

    for key in list(state.keys()):
        if str(key).startswith(GAMIFICATION_STATE_PREFIX):
            state.pop(key, None)


def queue_gamification_notifications(
    state: MutableMapping[str, Any],
    sync_result: dict | None,
) -> None:
    """새 업적 해금과 도전과제 완료를 다음 rerun 알림 큐에 넣습니다."""

    if not isinstance(sync_result, dict):
        return

    raw_unlocks = sync_result.get("newly_unlocked", [])
    if not isinstance(raw_unlocks, list):
        return

    existing_queue = state.get(NOTIFICATION_QUEUE_KEY, [])
    queue = list(existing_queue) if isinstance(existing_queue, list) else []
    queued_keys = {
        item.get("achievement_key")
        for item in queue
        if isinstance(item, dict)
    }

    for unlock in raw_unlocks:
        if not isinstance(unlock, dict):
            continue
        achievement_key = unlock.get("achievement_key")
        reward_exp = unlock.get("reward_exp")
        if (
            not isinstance(achievement_key, str)
            or not achievement_key
            or achievement_key in queued_keys
            or isinstance(reward_exp, bool)
            or not isinstance(reward_exp, int)
            or reward_exp <= 0
        ):
            continue
        queue.append(
            {
                "achievement_key": achievement_key,
                "reward_exp": reward_exp,
            }
        )
        queued_keys.add(achievement_key)

    raw_completions = sync_result.get(
        "newly_completed_challenges",
        [],
    )
    if isinstance(raw_completions, list):
        queued_challenge_ids = {
            item.get("challenge_id")
            for item in queue
            if isinstance(item, dict)
        }
        for completion in raw_completions:
            if not isinstance(completion, dict):
                continue
            challenge_id = completion.get("challenge_id")
            template_key = completion.get("template_key")
            if (
                not isinstance(challenge_id, str)
                or not challenge_id
                or challenge_id in queued_challenge_ids
                or not isinstance(template_key, str)
                or not template_key
            ):
                continue
            queue.append(
                {
                    "challenge_id": challenge_id,
                    "template_key": template_key,
                }
            )
            queued_challenge_ids.add(challenge_id)

    if queue:
        state[NOTIFICATION_QUEUE_KEY] = queue


def pop_gamification_notifications(
    state: MutableMapping[str, Any],
) -> list[dict]:
    """이번 rerun에 한 번 표시할 해금 알림을 꺼냅니다."""

    notifications = state.pop(NOTIFICATION_QUEUE_KEY, [])
    return notifications if isinstance(notifications, list) else []
