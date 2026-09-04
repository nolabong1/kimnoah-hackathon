from collections.abc import Mapping
from typing import Any

import streamlit as st

from services.reward_policy import EXP_PER_LEVEL
from views.streak_presentation import (
    get_streak_tier_label,
    resolve_streak_tier,
)


def build_learning_momentum(
    profile: Mapping[str, Any],
    *,
    completed_tasks: int,
    total_tasks: int,
) -> dict[str, Any]:
    """프로필과 오늘 과제 수치를 읽기 전용 학습 모멘텀으로 변환합니다."""

    total_exp = _require_non_negative_int(profile.get("total_exp"), "총 EXP")
    level = _require_positive_int(profile.get("level"), "레벨")
    current_streak = _require_non_negative_int(
        profile.get("current_streak"),
        "연속 학습일",
    )
    completed = _require_non_negative_int(completed_tasks, "완료 과제 수")
    total = _require_positive_int(total_tasks, "오늘 과제 수")
    if completed > total:
        raise ValueError("완료 과제 수는 오늘 과제 수보다 클 수 없습니다.")

    level_progress_exp = total_exp % EXP_PER_LEVEL
    today_progress_percent = round((completed / total) * 100)
    level_progress_percent = round(
        (level_progress_exp / EXP_PER_LEVEL) * 100
    )

    streak_tier = resolve_streak_tier(current_streak)
    if streak_tier == "legendary":
        streak_message = "30일의 꾸준함이 쌓였어요. 무리하지 말고 리듬을 지켜가세요."
    elif streak_tier == "blazing":
        streak_message = "두 주의 학습 흐름을 만들었어요. 오늘도 같은 시간에 이어가세요."
    elif streak_tier == "strong":
        streak_message = "꾸준한 학습 리듬이 단단하게 이어지고 있어요."
    elif streak_tier == "growing":
        streak_message = "좋은 흐름입니다. 오늘도 불꽃을 이어가세요."
    elif streak_tier == "spark":
        streak_message = "학습 불씨가 켜졌어요. 한 과제씩 이어가세요."
    else:
        streak_message = "오늘 첫 과제를 완료하면 학습 불씨가 시작됩니다."

    if completed == total:
        pace_message = "오늘 학습 루트를 모두 완주했습니다!"
    elif completed == 0:
        pace_message = "첫 노드를 선택하고 오늘의 학습을 시작해보세요."
    else:
        pace_message = f"{total - completed}개 과제를 더 완료하면 오늘 루트 완주!"

    return {
        "level": level,
        "total_exp": total_exp,
        "level_progress_exp": level_progress_exp,
        "level_progress_percent": level_progress_percent,
        "exp_to_next_level": EXP_PER_LEVEL - level_progress_exp,
        "current_streak": current_streak,
        "streak_tier": streak_tier,
        "streak_tier_label": get_streak_tier_label(streak_tier),
        "streak_message": streak_message,
        "completed_tasks": completed,
        "total_tasks": total,
        "today_progress_percent": today_progress_percent,
        "pace_message": pace_message,
        "today_complete": completed == total,
    }


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    normalized = _require_non_negative_int(value, field_name)
    if normalized == 0:
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return normalized


_MOMENTUM_HTML = """
<section class="momentum" aria-label="오늘의 학습 모멘텀">
  <div class="momentum__identity">
    <div class="momentum__flame" aria-hidden="true">
      <span class="momentum__flame-core"></span>
    </div>
    <div>
      <p class="momentum__eyebrow">학습 모멘텀</p>
      <span class="momentum__tier-badge"></span>
      <p class="momentum__streak-value"></p>
      <p class="momentum__streak-message"></p>
    </div>
  </div>

  <div class="momentum__today">
    <div class="momentum__ring" role="img">
      <div class="momentum__ring-center">
        <strong class="momentum__today-count"></strong>
        <span>오늘 과제</span>
      </div>
    </div>
    <p class="momentum__pace-message"></p>
  </div>

  <div class="momentum__level">
    <div class="momentum__level-heading">
      <span class="momentum__level-value"></span>
      <span class="momentum__level-exp"></span>
    </div>
    <div
      class="momentum__level-track"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <span class="momentum__level-fill"></span>
    </div>
    <p class="momentum__next-level"></p>
  </div>
</section>
"""


_MOMENTUM_CSS = """
.momentum {
  --momentum-accent: var(--st-primary-color);
  --today-progress: 0deg;
  --flame-scale: .78;
  --flame-aura-opacity: 0;
  --flame-speed: 1.35s;
  --flame-aura-speed: 2.8s;
  display: grid;
  grid-template-columns: 1.25fr 1fr 1.15fr;
  gap: 18px;
  box-sizing: border-box;
  width: 100%;
  padding: 18px 20px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background:
    linear-gradient(125deg, color-mix(in srgb, var(--momentum-accent) 9%, transparent), transparent 42%),
    var(--st-secondary-background-color);
  color: var(--st-text-color);
}

.momentum[data-tier="ready"] { --flame-main: #a7afc2; --flame-core: #d8dce7; }
.momentum[data-tier="spark"] { --flame-main: var(--st-orange-color, #ff9f43); --flame-core: #ffd166; --flame-scale: .9; }
.momentum[data-tier="growing"] { --flame-main: #ff7438; --flame-core: #ffd166; --flame-scale: 1; --flame-aura-opacity: .18; --flame-speed: 1.12s; --flame-aura-speed: 2.3s; }
.momentum[data-tier="strong"] { --flame-main: var(--st-red-color, #f44771); --flame-core: #ffca5f; --flame-scale: 1.08; --flame-aura-opacity: .32; --flame-speed: .9s; --flame-aura-speed: 1.9s; }
.momentum[data-tier="blazing"] { --flame-main: #e63973; --flame-core: #ffe38a; --flame-scale: 1.18; --flame-aura-opacity: .5; --flame-speed: .72s; --flame-aura-speed: 1.5s; --momentum-accent: var(--st-red-color, #e63973); }
.momentum[data-tier="legendary"] { --flame-main: var(--st-violet-color, #7b61ff); --flame-core: #fff0a8; --flame-scale: 1.28; --flame-aura-opacity: .72; --flame-speed: .58s; --flame-aura-speed: 1.2s; --momentum-accent: var(--st-violet-color, #7b61ff); }

.momentum[data-tier="blazing"],
.momentum[data-tier="legendary"] {
  border-color: color-mix(in srgb, var(--momentum-accent) 38%, var(--st-border-color));
  box-shadow: 0 10px 28px color-mix(in srgb, var(--momentum-accent) 13%, transparent);
}

.momentum__identity,
.momentum__today,
.momentum__level {
  min-width: 0;
}

.momentum__identity {
  display: flex;
  align-items: center;
  gap: 15px;
}

.momentum__flame {
  position: relative;
  flex: 0 0 56px;
  width: 56px;
  height: 66px;
  filter: drop-shadow(0 8px 12px color-mix(in srgb, var(--flame-main) 28%, transparent));
  transform: scale(var(--flame-scale));
  transition: filter 240ms ease, transform 240ms ease;
}

.momentum__flame::after {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 64px;
  height: 64px;
  border: 2px solid color-mix(in srgb, var(--flame-main) 62%, transparent);
  border-radius: 50%;
  box-shadow: 0 0 24px color-mix(in srgb, var(--flame-main) 40%, transparent);
  content: "";
  opacity: var(--flame-aura-opacity);
  transform: translateX(-50%) scale(.82);
  animation: flame-aura var(--flame-aura-speed) ease-in-out infinite;
}

.momentum__flame::before,
.momentum__flame-core {
  position: absolute;
  left: 50%;
  bottom: 6px;
  display: block;
  border-radius: 48% 52% 52% 48% / 58% 58% 42% 42%;
  content: "";
  transform: translateX(-50%) rotate(45deg);
  transform-origin: 50% 72%;
}

.momentum__flame::before {
  width: 43px;
  height: 43px;
  background: var(--flame-main);
  animation: flame-breathe var(--flame-speed) ease-in-out infinite alternate;
}

.momentum__flame-core {
  z-index: 1;
  width: 23px;
  height: 23px;
  background: var(--flame-core);
  animation: flame-core 1.1s ease-in-out infinite alternate;
}

.momentum[data-tier="ready"] .momentum__flame::before,
.momentum[data-tier="ready"] .momentum__flame-core,
.momentum[data-tier="ready"] .momentum__flame::after,
.momentum[data-tier="spark"] .momentum__flame::after {
  animation: none;
}

.momentum__eyebrow,
.momentum__tier-badge,
.momentum__streak-value,
.momentum__streak-message,
.momentum__pace-message,
.momentum__next-level {
  margin: 0;
}

.momentum__eyebrow {
  margin-bottom: 2px;
  color: var(--momentum-accent);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.momentum__tier-badge {
  display: inline-block;
  margin: 1px 0 4px;
  padding: 2px 7px;
  border: 1px solid color-mix(in srgb, var(--flame-main) 34%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--flame-main) 12%, transparent);
  color: var(--flame-main);
  font-size: .64rem;
  font-weight: 800;
}

.momentum__streak-value {
  font-size: 1.18rem;
  font-weight: 820;
}

.momentum__streak-message,
.momentum__pace-message,
.momentum__next-level {
  color: var(--st-text-color);
  font-size: 0.73rem;
  line-height: 1.45;
  opacity: 0.68;
}

.momentum__streak-message {
  margin-top: 4px;
}

.momentum__today {
  display: flex;
  align-items: center;
  gap: 12px;
  border-inline: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.12));
  padding-inline: 18px;
}

.momentum__ring {
  display: grid;
  flex: 0 0 66px;
  width: 66px;
  height: 66px;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(
    var(--momentum-accent) 0deg var(--today-progress),
    color-mix(in srgb, var(--st-text-color) 10%, transparent) var(--today-progress) 360deg
  );
  transition: background 300ms ease;
}

.momentum__ring-center {
  display: grid;
  width: 52px;
  height: 52px;
  place-items: center;
  align-content: center;
  border-radius: 50%;
  background: var(--st-secondary-background-color);
  line-height: 1.1;
}

.momentum__ring-center strong {
  font-size: 0.92rem;
}

.momentum__ring-center span {
  margin-top: 3px;
  font-size: 0.61rem;
  opacity: 0.6;
}

.momentum__level {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.momentum__level-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 9px;
}

.momentum__level-value {
  font-size: 0.92rem;
  font-weight: 800;
}

.momentum__level-exp {
  font-size: 0.7rem;
  opacity: 0.62;
}

.momentum__level-track {
  width: 100%;
  height: 9px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-text-color) 10%, transparent);
}

.momentum__level-fill {
  display: block;
  width: 0;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--momentum-accent), color-mix(in srgb, var(--momentum-accent) 55%, #f6c85f));
  transition: width 450ms cubic-bezier(.2,.8,.2,1);
}

.momentum__next-level {
  margin-top: 7px;
}

@keyframes flame-breathe {
  from { transform: translateX(-50%) rotate(43deg) scale(0.94, 1); }
  to { transform: translateX(-50%) rotate(47deg) scale(1.04, 1.09); }
}

@keyframes flame-core {
  from { transform: translateX(-50%) rotate(43deg) scale(0.88); }
  to { transform: translateX(-50%) rotate(47deg) scale(1.02); }
}

@keyframes flame-aura {
  0%, 100% { opacity: 0; transform: translateX(-50%) scale(.78); }
  50% { opacity: var(--flame-aura-opacity); transform: translateX(-50%) scale(1.08); }
}

@media (max-width: 760px) {
  .momentum {
    grid-template-columns: 1fr;
  }

  .momentum__today {
    border-inline: 0;
    border-block: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.12));
    padding: 14px 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .momentum__flame::before,
  .momentum__flame-core,
  .momentum__flame::after,
  .momentum__ring,
  .momentum__level-fill {
    animation: none;
    transition: none;
  }
}
"""


_MOMENTUM_JS = """
export default function (component) {
  const { data, parentElement } = component
  const root = parentElement.querySelector(".momentum")
  if (!root || !data) return

  const text = (selector, value) => {
    const target = parentElement.querySelector(selector)
    if (target) target.textContent = String(value)
  }

  const todayPercent = Math.max(0, Math.min(100, Number(data.today_progress_percent) || 0))
  const levelPercent = Math.max(0, Math.min(100, Number(data.level_progress_percent) || 0))
  root.dataset.tier = String(data.streak_tier || "ready")
  root.style.setProperty("--today-progress", `${todayPercent * 3.6}deg`)

  text(".momentum__streak-value", `${data.current_streak}일 연속 학습`)
  text(".momentum__tier-badge", data.streak_tier_label)
  text(".momentum__streak-message", data.streak_message)
  text(".momentum__today-count", `${data.completed_tasks}/${data.total_tasks}`)
  text(".momentum__pace-message", data.pace_message)
  text(".momentum__level-value", `레벨 ${data.level}`)
  text(".momentum__level-exp", `${data.level_progress_exp}/${data.exp_per_level} EXP`)
  text(".momentum__next-level", `다음 레벨까지 ${data.exp_to_next_level} EXP`)

  const ring = parentElement.querySelector(".momentum__ring")
  if (ring) ring.setAttribute("aria-label", `오늘 과제 ${todayPercent}% 완료`)

  const progress = parentElement.querySelector(".momentum__level-track")
  const fill = parentElement.querySelector(".momentum__level-fill")
  if (progress) progress.setAttribute("aria-valuenow", String(levelPercent))
  if (progress) progress.setAttribute("aria-label", `현재 레벨 EXP ${levelPercent}%`)
  if (fill) fill.style.width = `${levelPercent}%`

  return () => {
    root.style.removeProperty("--today-progress")
  }
}
"""


_LEARNING_MOMENTUM = st.components.v2.component(
    "learning_momentum_hud",
    html=_MOMENTUM_HTML,
    css=_MOMENTUM_CSS,
    js=_MOMENTUM_JS,
)


def render_learning_momentum(
    momentum: Mapping[str, Any],
    *,
    key: str,
) -> Any:
    """학습 모멘텀 HUD를 표시하며 미지원 테스트 환경은 안전하게 건너뜁니다."""

    payload = dict(momentum)
    payload["exp_per_level"] = EXP_PER_LEVEL
    try:
        return _LEARNING_MOMENTUM(
            key=key,
            data=payload,
            height="content",
        )
    except ValueError as error:
        if "Component 'learning_momentum_hud' is not registered" in str(error):
            return None
        raise
