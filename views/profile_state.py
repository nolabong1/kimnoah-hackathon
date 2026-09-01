from collections.abc import MutableMapping
from time import monotonic
from typing import Any

from services.profile_service import get_profile


PROFILE_STATE_PREFIX = "profile_snapshot_"
PROFILE_SNAPSHOT_KEY = f"{PROFILE_STATE_PREFIX}data"
PROFILE_USER_ID_KEY = f"{PROFILE_STATE_PREFIX}user_id"
PROFILE_LOADED_AT_KEY = f"{PROFILE_STATE_PREFIX}loaded_at"
PROFILE_CACHE_TTL_SECONDS = 30.0


def _is_non_negative_int(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_profile_snapshot(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    nickname = value.get("nickname")
    return (
        isinstance(nickname, str)
        and bool(nickname.strip())
        and _is_non_negative_int(value.get("total_exp"))
        and _is_non_negative_int(value.get("current_streak"))
        and isinstance(value.get("level"), int)
        and not isinstance(value.get("level"), bool)
        and value["level"] >= 1
    )


def get_profile_snapshot(
    client,
    user_id: str,
    state: MutableMapping[str, Any],
    *,
    now: float | None = None,
) -> dict:
    """짧은 세션 캐시를 사용해 반복 프로필 조회를 줄입니다."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("사용자 ID가 필요합니다.")

    current_time = monotonic() if now is None else float(now)
    snapshot = state.get(PROFILE_SNAPSHOT_KEY)
    loaded_at = state.get(PROFILE_LOADED_AT_KEY)
    cache_age = (
        current_time - loaded_at
        if isinstance(loaded_at, (int, float))
        and not isinstance(loaded_at, bool)
        else PROFILE_CACHE_TTL_SECONDS
    )
    cache_is_current = (
        state.get(PROFILE_USER_ID_KEY) == normalized_user_id
        and _is_profile_snapshot(snapshot)
        and 0 <= cache_age < PROFILE_CACHE_TTL_SECONDS
    )
    if cache_is_current:
        return dict(snapshot)

    loaded_profile = get_profile(client, normalized_user_id)
    if not _is_profile_snapshot(loaded_profile):
        raise RuntimeError("프로필 조회 결과가 올바르지 않습니다.")

    stored_snapshot = dict(loaded_profile)
    state[PROFILE_SNAPSHOT_KEY] = stored_snapshot
    state[PROFILE_USER_ID_KEY] = normalized_user_id
    state[PROFILE_LOADED_AT_KEY] = current_time
    return dict(stored_snapshot)


def update_profile_snapshot(
    state: MutableMapping[str, Any],
    result: object,
    *,
    now: float | None = None,
) -> bool:
    """서버 RPC의 확정값으로 기존 프로필 스냅샷을 즉시 갱신합니다."""

    snapshot = state.get(PROFILE_SNAPSHOT_KEY)
    if not _is_profile_snapshot(snapshot) or not isinstance(result, dict):
        return False

    updates: dict[str, int] = {}
    for field_name in ("total_exp", "current_streak"):
        if field_name not in result:
            continue
        field_value = result[field_name]
        if not _is_non_negative_int(field_value):
            return False
        updates[field_name] = field_value

    if "level" in result:
        level = result["level"]
        if (
            not isinstance(level, int)
            or isinstance(level, bool)
            or level < 1
        ):
            return False
        updates["level"] = level

    if not updates:
        return False

    updated_snapshot = dict(snapshot)
    updated_snapshot.update(updates)
    state[PROFILE_SNAPSHOT_KEY] = updated_snapshot
    state[PROFILE_LOADED_AT_KEY] = monotonic() if now is None else float(now)
    return True


def clear_profile_state(state: MutableMapping[str, Any]) -> None:
    """로그아웃 시 현재 사용자의 프로필 스냅샷만 제거합니다."""

    for key in list(state.keys()):
        if str(key).startswith(PROFILE_STATE_PREFIX):
            state.pop(key, None)
