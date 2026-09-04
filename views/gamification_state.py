from collections.abc import Callable, Mapping, MutableMapping
from time import monotonic
from typing import Any

from views.cache_config import DEFAULT_SESSION_CACHE_TTL_SECONDS
from views.profile_state import update_profile_snapshot


GAMIFICATION_STATE_PREFIX = "gamification_"
NOTIFICATION_QUEUE_KEY = "gamification_notification_queue"
SUCCESS_MESSAGE_KEY = "gamification_success_message"
SYNC_IN_PROGRESS_KEY = "gamification_sync_in_progress"
CLAIM_IN_PROGRESS_KEY = "gamification_claim_in_progress"
BADGE_IN_PROGRESS_KEY = "gamification_badge_in_progress"
PENDING_NAVIGATION_KEY = "gamification_pending_navigation"
ACTIVE_TAB_KEY = "gamification_active_tab"
DATA_SNAPSHOT_KEY = "gamification_data_snapshot"
DATA_USER_ID_KEY = "gamification_data_snapshot_user_id"
DATA_LOADED_AT_KEY = "gamification_data_snapshot_loaded_at"


def _copy_gamification_snapshot(
    snapshot: Mapping[str, Any],
) -> dict[str, list[dict]]:
    copied: dict[str, list[dict]] = {}
    for key in ("achievements", "challenges", "showcase"):
        value = snapshot.get(key)
        if not isinstance(value, list) or any(
            not isinstance(item, Mapping) for item in value
        ):
            raise RuntimeError("게임화 조회 결과가 올바르지 않습니다.")
        copied[key] = [dict(item) for item in value]
    return copied


def get_gamification_data_snapshot(
    state: MutableMapping[str, Any],
    user_id: str,
    loader: Callable[[], Mapping[str, Any]],
    *,
    now: float | None = None,
) -> dict[str, list[dict]]:
    """게임화 화면의 세 조회 결과를 사용자별로 짧게 재사용합니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")
    current_time = monotonic() if now is None else float(now)
    loaded_at = state.get(DATA_LOADED_AT_KEY)
    cached = state.get(DATA_SNAPSHOT_KEY)
    if (
        isinstance(cached, Mapping)
        and state.get(DATA_USER_ID_KEY) == normalized_user_id
        and isinstance(loaded_at, (int, float))
        and not isinstance(loaded_at, bool)
        and 0 <= current_time - loaded_at < DEFAULT_SESSION_CACHE_TTL_SECONDS
    ):
        return _copy_gamification_snapshot(cached)

    loaded = loader()
    if not isinstance(loaded, Mapping):
        raise RuntimeError("게임화 조회 결과가 올바르지 않습니다.")
    snapshot = _copy_gamification_snapshot(loaded)
    state[DATA_SNAPSHOT_KEY] = snapshot
    state[DATA_USER_ID_KEY] = normalized_user_id
    state[DATA_LOADED_AT_KEY] = current_time
    return _copy_gamification_snapshot(snapshot)


def invalidate_gamification_data_snapshot(
    state: MutableMapping[str, Any],
) -> None:
    """게임화 쓰기 성공 뒤 다음 조회가 서버 상태를 반영하게 합니다."""

    for key in (
        DATA_SNAPSHOT_KEY,
        DATA_USER_ID_KEY,
        DATA_LOADED_AT_KEY,
    ):
        state.pop(key, None)


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

    update_profile_snapshot(state, sync_result)
    invalidate_gamification_data_snapshot(state)

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
