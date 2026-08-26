from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

import streamlit as st

from services.error_reporting import report_exception
from models.gamification import (
    AchievementCategory,
    ChallengePeriodType,
    ChallengeStatus,
)
from services.gamification_catalog import (
    ACHIEVEMENT_CATALOG,
    ACHIEVEMENTS_BY_KEY,
    CHALLENGE_TEMPLATES_BY_KEY,
)
from services.gamification_repository import (
    claim_challenge_reward,
    equip_badge,
    get_badge_showcase,
    get_user_achievements,
    get_user_challenges,
    remove_badge,
    sync_gamification_state,
)
from services.gamification_service import (
    get_period_window,
    mask_achievement_definition,
)
from views.gamification_state import (
    BADGE_IN_PROGRESS_KEY,
    CLAIM_IN_PROGRESS_KEY,
    PENDING_NAVIGATION_KEY,
    SUCCESS_MESSAGE_KEY,
    SYNC_IN_PROGRESS_KEY,
    pop_gamification_notifications,
    queue_gamification_notifications,
)
from views.error_feedback import render_unexpected_error
from views.ui_components import (
    MetricItem,
    render_metric_row,
    render_page_header,
)


SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
ACHIEVEMENT_FILTER_KEY = "gamification_achievement_category_filter"

CATEGORY_LABELS = {
    AchievementCategory.TASK: "과제",
    AchievementCategory.STREAK: "연속 학습",
    AchievementCategory.PLAN: "계획",
    AchievementCategory.REVIEW: "복습",
    AchievementCategory.QUIZ: "퀴즈",
    AchievementCategory.BALANCE: "균형",
}
TIER_LABELS = {
    "bronze": "브론즈",
    "silver": "실버",
    "gold": "골드",
    "platinum": "플래티넘",
}
RARITY_LABELS = {
    "common": "일반",
    "uncommon": "고급",
    "rare": "희귀",
    "epic": "영웅",
    "legendary": "전설",
}


def render_gamification_notifications() -> None:
    """학습 행동 뒤 큐에 저장된 업적 해금을 한 번만 알립니다."""

    notifications = pop_gamification_notifications(st.session_state)
    for notification in notifications:
        if "achievement_key" in notification:
            definition = ACHIEVEMENTS_BY_KEY.get(
                notification.get("achievement_key")
            )
            if definition is None:
                continue
            st.toast(
                f"{definition.badge.icon} 업적 해금: "
                f"{definition.name_ko} · +{notification['reward_exp']} EXP",
                icon=definition.badge.icon,
            )
            continue

        template = CHALLENGE_TEMPLATES_BY_KEY.get(
            notification.get("template_key")
        )
        if template is not None:
            st.toast(
                f"도전과제 완료: {template.name_ko} · 보상을 받아보세요.",
                icon="🎯",
            )


def render_gamification_page(supabase, user) -> None:
    """업적·도전과제·배지 보관함 화면을 표시합니다."""

    render_page_header(
        "업적·도전과제",
        "학습 기록으로 도전과제를 달성하고 획득한 배지를 관리합니다.",
    )
    st.caption(
        "도전과제 보상은 완료 후 직접 수령해야 하며, "
        "일간은 서울 자정·주간은 월요일 서울 자정에 새로 시작합니다."
    )

    user_id = getattr(user, "id", None)
    if user_id is None:
        st.error("로그인 정보를 확인할 수 없습니다. 다시 로그인해주세요.")
        return

    if SUCCESS_MESSAGE_KEY in st.session_state:
        st.success(st.session_state.pop(SUCCESS_MESSAGE_KEY))

    sync_running = bool(
        st.session_state.get(SYNC_IN_PROGRESS_KEY, False)
    )
    if st.button(
        "학습 기록 새로 반영하기",
        key="gamification_sync_button",
        icon=":material/sync:",
        disabled=sync_running,
        help=(
            "저장된 과제 완료와 퀴즈 응시 기록을 서버에서 다시 확인합니다. "
            "화면 새로고침만으로는 보상을 평가하지 않습니다."
        ),
    ):
        st.session_state[SYNC_IN_PROGRESS_KEY] = True
        try:
            with st.spinner("학습 기록과 도전과제를 확인하고 있습니다..."):
                sync_result = sync_gamification_state(supabase)
            queue_gamification_notifications(
                st.session_state,
                sync_result,
            )
            st.session_state[SUCCESS_MESSAGE_KEY] = (
                "현재 학습 기록을 업적과 도전과제에 반영했습니다."
            )
            st.rerun()
        except Exception as error:
            render_unexpected_error(
                error,
                operation="gamification.sync",
                user_message=_friendly_gamification_error(error),
            )
        finally:
            st.session_state[SYNC_IN_PROGRESS_KEY] = False

    try:
        achievements = get_user_achievements(supabase, str(user_id))
    except Exception as error:
        render_unexpected_error(
            error,
            operation="gamification.load_achievements",
            user_message=(
                "업적 데이터를 불러오지 못했습니다. "
                + _friendly_gamification_error(error)
            ),
        )
        return

    try:
        challenges = get_user_challenges(supabase, str(user_id))
    except Exception as error:
        render_unexpected_error(
            error,
            operation="gamification.load_challenges",
            user_message=(
                "도전과제 데이터를 불러오지 못했습니다. "
                + _friendly_gamification_error(error)
            ),
        )
        return

    try:
        showcase = get_badge_showcase(supabase, str(user_id))
    except Exception as error:
        render_unexpected_error(
            error,
            operation="gamification.load_showcase",
            user_message=(
                "대표 배지 데이터를 불러오지 못했습니다. "
                + _friendly_gamification_error(error)
            ),
        )
        return

    unlocked_count = sum(
        achievement.get("unlocked_at") is not None
        for achievement in achievements
    )
    completed_challenge_count = sum(
        challenge["status"] == ChallengeStatus.COMPLETED.value
        for challenge in challenges
    )
    claimed_challenge_count = sum(
        challenge["status"] == ChallengeStatus.CLAIMED.value
        for challenge in challenges
    )
    render_metric_row(
        [
            MetricItem("해금한 업적", f"{unlocked_count}개"),
            MetricItem("수령 가능 보상", f"{completed_challenge_count}개"),
            MetricItem("수령한 도전 보상", f"{claimed_challenge_count}개"),
            MetricItem("대표 배지", f"{len(showcase)}/3개"),
        ]
    )

    challenge_tab, achievement_tab, badge_tab = st.tabs(
        [
            "도전과제",
            "업적",
            "배지 보관함",
        ]
    )

    with challenge_tab:
        _render_challenges(supabase, challenges)

    with achievement_tab:
        _render_achievements(achievements)

    with badge_tab:
        _render_badges(supabase, achievements, showcase)


def render_gamification_dashboard_summary(
    supabase,
    user_id: str,
) -> None:
    """오늘 학습 화면에 읽기 전용 게임화 요약을 작게 표시합니다."""

    try:
        achievements = get_user_achievements(supabase, user_id)
        challenges = get_user_challenges(supabase, user_id)
        showcase = get_badge_showcase(supabase, user_id)
    except Exception as error:
        report_exception("gamification.load_dashboard_summary", error)
        return

    render_gamification_dashboard_summary_from_data(
        achievements=achievements,
        challenges=challenges,
        showcase=showcase,
    )


def render_gamification_dashboard_summary_from_data(
    achievements: list[dict],
    challenges: list[dict],
    showcase: list[dict],
) -> None:
    """이미 조회한 게임화 데이터로 오늘의 성장 요약을 표시합니다."""

    now = datetime.now(timezone.utc)
    daily_window = get_period_window(
        ChallengePeriodType.DAILY,
        now,
    )
    current_daily = _get_current_challenges(
        challenges,
        daily_window.start_at,
        ChallengePeriodType.DAILY,
    )
    completed_daily = sum(
        challenge["status"]
        in {ChallengeStatus.COMPLETED.value, ChallengeStatus.CLAIMED.value}
        for challenge in current_daily
    )
    unlocked = sorted(
        (
            achievement
            for achievement in achievements
            if achievement.get("unlocked_at")
        ),
        key=lambda item: item["unlocked_at"],
        reverse=True,
    )
    recent_definition = (
        ACHIEVEMENTS_BY_KEY.get(unlocked[0]["achievement_key"])
        if unlocked
        else None
    )
    showcase_definitions = [
        ACHIEVEMENTS_BY_KEY.get(slot["achievement_key"])
        for slot in sorted(showcase, key=lambda item: item["slot"])
    ]
    showcase_icons = " ".join(
        definition.badge.icon
        for definition in showcase_definitions
        if definition is not None
    )

    with st.container(border=True):
        st.markdown("### 오늘의 성장")
        with st.container(horizontal=True):
            st.metric(
                "일간 도전과제",
                f"{completed_daily}/{len(current_daily)}",
                border=True,
            )
            st.metric(
                "최근 획득 배지",
                (
                    recent_definition.badge.name_ko
                    if recent_definition
                    else "아직 없음"
                ),
                border=True,
            )

        st.caption(f"대표 배지 · {showcase_icons or '미설정'}")

        if not achievements and not challenges:
            st.caption(
                "성장 화면에서 학습 기록을 반영하면 업적과 도전과제가 시작됩니다."
            )

        if st.button(
            "업적·도전과제 보기",
            key="gamification_dashboard_open_button",
            icon=":material/military_tech:",
        ):
            st.session_state[PENDING_NAVIGATION_KEY] = "업적·도전과제"
            st.rerun()


def _render_challenges(supabase, challenges: list[dict]) -> None:
    """현재 일간·주간 및 이전 미수령 도전과제를 표시합니다."""

    st.subheader("현재 도전과제")
    now = datetime.now(timezone.utc)
    daily_window = get_period_window(ChallengePeriodType.DAILY, now)
    weekly_window = get_period_window(ChallengePeriodType.WEEKLY, now)
    current_daily = _get_current_challenges(
        challenges,
        daily_window.start_at,
        ChallengePeriodType.DAILY,
    )
    current_weekly = _get_current_challenges(
        challenges,
        weekly_window.start_at,
        ChallengePeriodType.WEEKLY,
    )

    st.markdown("#### 오늘")
    _render_challenge_group(supabase, current_daily, now)
    st.markdown("#### 이번 주")
    _render_challenge_group(supabase, current_weekly, now)

    current_ids = {
        challenge["id"]
        for challenge in current_daily + current_weekly
    }
    previous_claimable = [
        challenge
        for challenge in challenges
        if challenge["status"] == ChallengeStatus.COMPLETED.value
        and challenge["id"] not in current_ids
    ]
    if previous_claimable:
        st.markdown("#### 이전 기간 미수령 보상")
        _render_challenge_group(supabase, previous_claimable, now)


def _render_challenge_group(
    supabase,
    challenges: list[dict],
    now: datetime,
) -> None:
    """같은 기간의 도전과제 카드와 수령 동작을 표시합니다."""

    if not challenges:
        st.info(
            "현재 배정된 도전과제가 없습니다. 수행 가능한 과제나 퀴즈가 "
            "있는지 확인한 뒤 학습 기록을 새로 반영해주세요."
        )
        return

    challenge_columns = st.columns(min(3, len(challenges)), gap="medium")
    for index, challenge in enumerate(challenges):
        template = CHALLENGE_TEMPLATES_BY_KEY.get(challenge["template_key"])
        if template is None:
            st.warning("지원하지 않는 도전과제 기록이 있어 표시하지 못했습니다.")
            continue

        progress_value = min(
            challenge["progress_value"],
            challenge["target_value"],
        )
        status = challenge["status"]
        with challenge_columns[index % len(challenge_columns)]:
            with st.container(border=True):
                st.caption(
                    "보상 수령 완료"
                    if status == ChallengeStatus.CLAIMED.value
                    else (
                        "보상 수령 가능"
                        if status == ChallengeStatus.COMPLETED.value
                        else "진행 중"
                    )
                )
                st.markdown(f"### {template.name_ko}")
                st.write(template.description_ko)
                st.progress(
                    progress_value / challenge["target_value"],
                    text=(
                        f"진행 {progress_value}/{challenge['target_value']}"
                    ),
                )
                st.caption(
                    f"보상 {challenge['reward_exp']} EXP · "
                    + _challenge_period_label(challenge, now)
                )

                if status == ChallengeStatus.CLAIMED.value:
                    st.success("보상을 수령했습니다.")
                elif status == ChallengeStatus.COMPLETED.value:
                    st.success("완료했습니다. 보상을 수령할 수 있습니다.")
                    _render_claim_button(supabase, challenge)
                elif status == ChallengeStatus.EXPIRED.value:
                    st.caption("완료하지 못한 채 기간이 종료되었습니다.")


def _render_claim_button(supabase, challenge: dict) -> None:
    """도전과제 보상을 명시적으로 한 번 수령합니다."""

    in_progress_id = st.session_state.get(CLAIM_IN_PROGRESS_KEY)
    if st.button(
        "보상 받기",
        key=f"gamification_claim_{challenge['id']}",
        type="primary",
        icon=":material/redeem:",
        disabled=in_progress_id is not None,
    ):
        st.session_state[CLAIM_IN_PROGRESS_KEY] = challenge["id"]
        try:
            with st.spinner("보상을 안전하게 지급하고 있습니다..."):
                result = claim_challenge_reward(
                    supabase,
                    challenge["id"],
                )
            st.session_state[SUCCESS_MESSAGE_KEY] = (
                "이미 수령한 보상입니다."
                if result["already_claimed"]
                else f"도전과제 보상 {result['reward_exp']} EXP를 받았습니다."
            )
            st.rerun()
        except Exception as error:
            render_unexpected_error(
                error,
                operation="gamification.claim_challenge",
                user_message=_friendly_gamification_error(error),
            )
        finally:
            st.session_state.pop(CLAIM_IN_PROGRESS_KEY, None)


def _render_achievements(achievements: list[dict]) -> None:
    """카테고리 필터와 함께 전체 업적 진행도를 표시합니다."""

    achievement_by_key = {
        achievement["achievement_key"]: achievement
        for achievement in achievements
    }
    unlocked_count = sum(
        achievement.get("unlocked_at") is not None
        for achievement in achievements
    )

    with st.container(horizontal=True):
        st.metric(
            "해금한 업적",
            f"{unlocked_count}/{len(ACHIEVEMENT_CATALOG)}",
            border=True,
        )
        st.metric(
            "획득한 배지",
            f"{unlocked_count}개",
            border=True,
        )

    category_options = ["전체", *CATEGORY_LABELS.values()]
    selected_category = st.selectbox(
        "업적 카테고리",
        options=category_options,
        key=ACHIEVEMENT_FILTER_KEY,
        persist_state="session",
    )
    visible_definitions = [
        definition
        for definition in ACHIEVEMENT_CATALOG
        if selected_category == "전체"
        or CATEGORY_LABELS[definition.category] == selected_category
    ]

    achievement_columns = st.columns(2, gap="medium")
    for index, definition in enumerate(visible_definitions):
        state = achievement_by_key.get(definition.key, {})
        unlocked_at = state.get("unlocked_at")
        display = mask_achievement_definition(
            definition,
            is_unlocked=bool(unlocked_at),
        )

        with achievement_columns[index % 2]:
            with st.container(border=True):
                st.caption("해금 완료" if unlocked_at else "잠긴 업적")
                st.markdown(
                    f"### {display['badge']['icon'] if unlocked_at else '🔒'} "
                    f"{display['name_ko']}"
                )
                st.write(display["description_ko"])
                if display["target_value"] is None:
                    st.caption(
                        "비밀 업적 · 달성 조건과 보상은 해금 후 공개됩니다."
                    )
                else:
                    progress_value = min(
                        int(state.get("progress_value", 0)),
                        display["target_value"],
                    )
                    st.progress(
                        progress_value / display["target_value"],
                        text=(
                            "진행 "
                            f"{progress_value}/{display['target_value']}"
                        ),
                    )
                    st.caption(
                        f"{TIER_LABELS[display['tier']]} · "
                        f"{RARITY_LABELS[display['badge']['rarity']]} 배지 · "
                        f"보상 {display['reward_exp']} EXP"
                    )
                if unlocked_at:
                    st.success(
                        "해금일 · " + _format_seoul_datetime(unlocked_at)
                    )
                else:
                    st.caption("아직 잠겨 있습니다.")


def _render_badges(
    supabase,
    achievements: list[dict],
    showcase: list[dict],
) -> None:
    """획득 배지와 대표 배지 세 슬롯을 표시합니다."""

    unlocked_by_key = {
        achievement["achievement_key"]: achievement
        for achievement in achievements
        if achievement.get("unlocked_at")
        and achievement["achievement_key"] in ACHIEVEMENTS_BY_KEY
    }
    showcase_by_slot = {
        item["slot"]: item
        for item in showcase
    }
    showcase_slot_by_key = {
        item["achievement_key"]: item["slot"]
        for item in showcase
    }

    st.subheader("대표 배지")
    st.caption("획득한 배지 중 최대 3개를 프로필 대표 배지로 설정합니다.")

    options = [None, *unlocked_by_key.keys()]
    slot_columns = st.columns(3, gap="medium")
    for slot in range(1, 4):
        current_key = showcase_by_slot.get(slot, {}).get("achievement_key")
        widget_key = f"gamification_badge_slot_{slot}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = current_key
        elif st.session_state[widget_key] not in options:
            st.session_state[widget_key] = current_key

        with slot_columns[slot - 1]:
            with st.container(border=True):
                selected_key = st.selectbox(
                    f"대표 배지 {slot}",
                    options=options,
                    key=widget_key,
                    format_func=lambda key: (
                        "비워두기"
                        if key is None
                        else (
                            f"{ACHIEVEMENTS_BY_KEY[key].badge.icon} "
                            f"{ACHIEVEMENTS_BY_KEY[key].badge.name_ko}"
                        )
                    ),
                    persist_state="session",
                )
                if st.button(
                    "대표 배지 적용",
                    key=f"gamification_badge_apply_{slot}",
                    icon=":material/check:",
                    width="stretch",
                    disabled=(
                        selected_key == current_key
                        or st.session_state.get(BADGE_IN_PROGRESS_KEY)
                        is not None
                    ),
                ):
                    _apply_badge_selection(
                        supabase,
                        slot,
                        selected_key,
                    )

    st.subheader("배지 컬렉션")
    badge_columns = st.columns(3, gap="medium")
    for index, definition in enumerate(ACHIEVEMENT_CATALOG):
        achievement = unlocked_by_key.get(definition.key)
        display = mask_achievement_definition(
            definition,
            is_unlocked=achievement is not None,
        )
        with badge_columns[index % 3]:
            with st.container(border=True):
                st.caption("획득한 배지" if achievement else "잠긴 배지")
                st.markdown(
                    f"### {display['badge']['icon'] if achievement else '🔒'} "
                    f"{display['badge']['name_ko']}"
                )
                if display["badge"]["rarity"] is not None:
                    st.caption(
                        "희귀도 · "
                        f"{RARITY_LABELS[display['badge']['rarity']]}"
                    )
                st.write(display["description_ko"])
                if achievement:
                    st.caption(
                        "획득일 · "
                        + _format_seoul_datetime(
                            achievement["unlocked_at"]
                        )
                    )
                    if definition.key in showcase_slot_by_key:
                        st.success(
                            "대표 배지 "
                            f"{showcase_slot_by_key[definition.key]}번에 설정됨"
                        )
                elif display["hidden"]:
                    st.caption("달성 조건과 배지는 해금 후 공개됩니다.")
                else:
                    st.caption("표시된 업적 조건을 달성하면 획득할 수 있습니다.")


def _apply_badge_selection(
    supabase,
    slot: int,
    selected_key: str | None,
) -> None:
    """선택한 대표 배지를 서버 RPC로 장착하거나 제거합니다."""

    st.session_state[BADGE_IN_PROGRESS_KEY] = slot
    try:
        with st.spinner("대표 배지를 변경하고 있습니다..."):
            if selected_key is None:
                remove_badge(supabase, slot)
                message = f"대표 배지 {slot}번 슬롯을 비웠습니다."
            else:
                equip_badge(supabase, selected_key, slot)
                definition = ACHIEVEMENTS_BY_KEY[selected_key]
                message = (
                    f"{definition.badge.icon} {definition.badge.name_ko}를 "
                    f"대표 배지 {slot}번에 설정했습니다."
                )
        st.session_state[SUCCESS_MESSAGE_KEY] = message
        st.rerun()
    except Exception as error:
        render_unexpected_error(
            error,
            operation="gamification.update_badge",
            user_message=_friendly_gamification_error(error),
        )
    finally:
        st.session_state.pop(BADGE_IN_PROGRESS_KEY, None)


def _get_current_challenges(
    challenges: list[dict],
    period_start: datetime,
    period_type: ChallengePeriodType,
) -> list[dict]:
    """정확한 현재 기간에 저장된 도전과제를 표시 순서대로 반환합니다."""

    return sorted(
        (
            challenge
            for challenge in challenges
            if challenge["period_type"] == period_type.value
            and _parse_datetime(challenge["period_start"]) == period_start
        ),
        key=lambda item: item["display_order"],
    )


def _challenge_period_label(challenge: dict, now: datetime) -> str:
    """도전과제 상태에 맞는 남은 기간 또는 종료일을 표시합니다."""

    if challenge["status"] == ChallengeStatus.COMPLETED.value:
        return "기간이 지나도 보상 수령 가능"
    if challenge["status"] == ChallengeStatus.CLAIMED.value:
        return "보상 수령 완료"

    period_end = _parse_datetime(challenge["period_end"])
    if now >= period_end:
        return "기간 종료"
    remaining_hours = max(
        1,
        ceil((period_end - now).total_seconds() / 3600),
    )
    if remaining_hours < 24:
        return f"약 {remaining_hours}시간 남음"
    return f"약 {ceil(remaining_hours / 24)}일 남음"


def _parse_datetime(value: str | datetime) -> datetime:
    """Supabase timestamptz 값을 시간대 포함 datetime으로 변환합니다."""

    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("시간대 없는 게임화 날짜입니다.")
    return parsed


def _format_seoul_datetime(value: str | datetime) -> str:
    """저장 시각을 서울 기준 분 단위로 표시합니다."""

    return _parse_datetime(value).astimezone(SEOUL_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M"
    )


def _friendly_gamification_error(error: Exception) -> str:
    """내부 응답을 노출하지 않고 알려진 게임화 오류를 한국어로 안내합니다."""

    raw_message = str(error)
    known_messages = (
        "아직 완료하지 않은 도전과제입니다.",
        "기간 안에 완료하지 못한 도전과제입니다.",
        "아직 획득하지 않은 배지입니다.",
        "같은 배지를 여러 슬롯에 장착할 수 없습니다.",
        "대표 배지 슬롯은 1부터 3 사이여야 합니다.",
        "도전과제를 찾을 수 없습니다.",
        "로그인이 필요합니다.",
        "사용자 프로필을 찾을 수 없습니다.",
    )
    for message in known_messages:
        if message in raw_message:
            return message
    if any(
        marker in raw_message
        for marker in (
            "user_achievements",
            "user_challenges",
            "sync_gamification_state",
            "PGRST202",
            "PGRST205",
        )
    ):
        return (
            "게임화 데이터베이스 설정이 아직 적용되지 않았습니다. "
            "필수 Supabase SQL 마이그레이션을 확인해주세요."
        )
    if "지원하지 않는 게임화 지표" in raw_message:
        return "지원하지 않는 학습 기록이 있어 진행도를 계산하지 못했습니다."
    if "서버 카탈로그와 다릅니다" in raw_message:
        return "저장된 게임화 보상 정보의 일관성을 확인하지 못했습니다."
    return "게임화 정보를 처리하지 못했습니다. 잠시 후 다시 시도해주세요."
