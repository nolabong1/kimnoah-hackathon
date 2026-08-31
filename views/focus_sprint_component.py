from collections.abc import Mapping
from typing import Any

import streamlit as st


MAX_FOCUS_MINUTES = 25
ALLOWED_TIMER_PHASES = {"ready", "running", "paused", "completed"}


def build_focus_sprint_config(task: Mapping[str, Any]) -> dict[str, Any]:
    """과제 정보에서 비용 없는 집중 스프린트 설정을 만듭니다."""

    task_id = task.get("id")
    title = task.get("title")
    estimated_minutes = task.get("estimated_minutes")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("집중 타이머 과제 ID가 올바르지 않습니다.")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("집중 타이머 과제 제목이 올바르지 않습니다.")
    if (
        isinstance(estimated_minutes, bool)
        or not isinstance(estimated_minutes, int)
        or not 1 <= estimated_minutes <= 1440
    ):
        raise ValueError("집중 타이머 예상 학습시간이 올바르지 않습니다.")

    duration_minutes = min(estimated_minutes, MAX_FOCUS_MINUTES)
    return {
        "task_id": task_id.strip(),
        "title": " ".join(title.split()),
        "duration_minutes": duration_minutes,
        "duration_seconds": duration_minutes * 60,
        "is_capped": estimated_minutes > MAX_FOCUS_MINUTES,
    }


def normalize_focus_timer_state(
    value: object,
    *,
    duration_seconds: int,
) -> dict[str, Any]:
    """브라우저가 보낸 타이머 상태를 표시 가능한 제한된 값으로 검증합니다."""

    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or duration_seconds <= 0
    ):
        raise ValueError("집중 타이머 기본 시간이 올바르지 않습니다.")

    default_state = {
        "phase": "ready",
        "remaining_seconds": duration_seconds,
        "target_at_ms": None,
    }
    if not isinstance(value, Mapping):
        return default_state

    phase = value.get("phase")
    remaining_seconds = value.get("remaining_seconds")
    target_at_ms = value.get("target_at_ms")
    if phase not in ALLOWED_TIMER_PHASES:
        return default_state
    if (
        isinstance(remaining_seconds, bool)
        or not isinstance(remaining_seconds, int)
        or not 0 <= remaining_seconds <= duration_seconds
    ):
        return default_state

    if phase == "completed":
        return {
            "phase": "completed",
            "remaining_seconds": 0,
            "target_at_ms": None,
        }
    if phase == "ready":
        return default_state
    if phase == "running":
        if (
            isinstance(target_at_ms, bool)
            or not isinstance(target_at_ms, (int, float))
            or target_at_ms <= 0
        ):
            return default_state
        return {
            "phase": "running",
            "remaining_seconds": remaining_seconds,
            "target_at_ms": int(target_at_ms),
        }

    return {
        "phase": "paused",
        "remaining_seconds": remaining_seconds,
        "target_at_ms": None,
    }


_FOCUS_SPRINT_HTML = """
<section class="focus-sprint" aria-label="집중 스프린트 타이머">
  <div class="focus-sprint__header">
    <div>
      <p class="focus-sprint__eyebrow">집중 스프린트</p>
      <p class="focus-sprint__title"></p>
    </div>
    <span class="focus-sprint__status"></span>
  </div>

  <div class="focus-sprint__body">
    <div class="focus-sprint__dial" role="timer" aria-live="off">
      <div class="focus-sprint__dial-center">
        <strong class="focus-sprint__time"></strong>
        <span class="focus-sprint__time-label">남은 집중시간</span>
      </div>
    </div>
    <div class="focus-sprint__controls">
      <p class="focus-sprint__message"></p>
      <div class="focus-sprint__buttons">
        <button type="button" class="focus-sprint__main"></button>
        <button type="button" class="focus-sprint__reset">초기화</button>
      </div>
    </div>
  </div>

  <p class="focus-sprint__notice">
    집중 보조용 타이머입니다. 종료되어도 과제가 자동 완료되거나 EXP가 지급되지 않습니다.
  </p>
</section>
"""


_FOCUS_SPRINT_CSS = """
.focus-sprint {
  --sprint-progress: 360deg;
  box-sizing: border-box;
  width: 100%;
  margin: 4px 0 14px;
  padding: 16px 18px 13px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background:
    radial-gradient(circle at 6% 0%, color-mix(in srgb, var(--st-primary-color) 12%, transparent), transparent 34%),
    var(--st-secondary-background-color);
  color: var(--st-text-color);
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.focus-sprint.is-running {
  border-color: color-mix(in srgb, var(--st-primary-color) 45%, transparent);
  box-shadow: 0 9px 24px color-mix(in srgb, var(--st-primary-color) 10%, transparent);
}

.focus-sprint.is-completed {
  border-color: color-mix(in srgb, #25a865 55%, transparent);
  background:
    radial-gradient(circle at 8% 0%, rgba(37, 168, 101, 0.15), transparent 38%),
    var(--st-secondary-background-color);
  animation: sprint-complete 560ms cubic-bezier(.18,.85,.32,1.18);
}

.focus-sprint__header,
.focus-sprint__body,
.focus-sprint__buttons {
  display: flex;
  align-items: center;
}

.focus-sprint__header {
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.focus-sprint__eyebrow,
.focus-sprint__title,
.focus-sprint__message,
.focus-sprint__notice {
  margin: 0;
}

.focus-sprint__eyebrow {
  color: var(--st-primary-color);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.focus-sprint__title {
  max-width: 430px;
  margin-top: 2px;
  overflow: hidden;
  font-size: 0.88rem;
  font-weight: 760;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.focus-sprint__status {
  flex: 0 0 auto;
  padding: 5px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-primary-color) 12%, transparent);
  color: var(--st-primary-color);
  font-size: 0.68rem;
  font-weight: 780;
}

.focus-sprint__body {
  gap: 18px;
}

.focus-sprint__dial {
  display: grid;
  flex: 0 0 88px;
  width: 88px;
  height: 88px;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(
    var(--st-primary-color) 0deg var(--sprint-progress),
    color-mix(in srgb, var(--st-text-color) 10%, transparent) var(--sprint-progress) 360deg
  );
  transition: background 200ms linear, transform 180ms ease;
}

.focus-sprint.is-running .focus-sprint__dial {
  transform: scale(1.025);
}

.focus-sprint.is-completed .focus-sprint__dial {
  background: #25a865;
}

.focus-sprint__dial-center {
  display: grid;
  width: 72px;
  height: 72px;
  place-items: center;
  align-content: center;
  border-radius: 50%;
  background: var(--st-secondary-background-color);
  line-height: 1.08;
}

.focus-sprint__time {
  font-variant-numeric: tabular-nums;
  font-size: 1.12rem;
}

.focus-sprint__time-label {
  margin-top: 4px;
  font-size: 0.6rem;
  opacity: 0.6;
}

.focus-sprint__controls {
  flex: 1 1 auto;
  align-items: stretch;
  flex-direction: column;
  gap: 11px;
}

.focus-sprint__message {
  min-height: 2.8em;
  font-size: 0.77rem;
  line-height: 1.45;
  opacity: 0.74;
}

.focus-sprint__buttons {
  gap: 8px;
}

.focus-sprint button {
  min-height: 36px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: calc(var(--st-border-radius, 12px) - 3px);
  padding: 7px 13px;
  background: var(--st-background-color);
  color: var(--st-text-color);
  cursor: pointer;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 750;
  transition: transform 130ms ease, box-shadow 130ms ease, border-color 130ms ease;
}

.focus-sprint button:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--st-primary-color);
  box-shadow: 0 5px 12px color-mix(in srgb, var(--st-primary-color) 12%, transparent);
}

.focus-sprint button:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--st-primary-color) 28%, transparent);
  outline-offset: 2px;
}

.focus-sprint__main {
  flex: 1 1 auto;
  border-color: var(--st-primary-color) !important;
  background: var(--st-primary-color) !important;
  color: white !important;
}

.focus-sprint button:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.focus-sprint__notice {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.1));
  font-size: 0.66rem;
  line-height: 1.4;
  opacity: 0.58;
}

@keyframes sprint-complete {
  0% { transform: scale(0.98); }
  55% { transform: scale(1.012); }
  100% { transform: scale(1); }
}

@media (max-width: 620px) {
  .focus-sprint__body {
    align-items: flex-start;
  }

  .focus-sprint__title {
    max-width: 260px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .focus-sprint,
  .focus-sprint__dial,
  .focus-sprint button {
    animation: none;
    transition: none;
  }
}
"""


_FOCUS_SPRINT_JS = """
const activeIntervals = new WeakMap()

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const root = parentElement.querySelector(".focus-sprint")
  const time = parentElement.querySelector(".focus-sprint__time")
  const title = parentElement.querySelector(".focus-sprint__title")
  const status = parentElement.querySelector(".focus-sprint__status")
  const message = parentElement.querySelector(".focus-sprint__message")
  const mainButton = parentElement.querySelector(".focus-sprint__main")
  const resetButton = parentElement.querySelector(".focus-sprint__reset")
  const dial = parentElement.querySelector(".focus-sprint__dial")
  if (!root || !time || !title || !status || !message || !mainButton || !resetButton || !dial) return

  const previousInterval = activeIntervals.get(parentElement)
  if (previousInterval) window.clearInterval(previousInterval)

  const config = data?.config || {}
  let timer = { ...(data?.timer || {}) }
  const duration = Math.max(1, Number(config.duration_seconds) || 1)
  let completedEmitted = timer.phase === "completed"

  const formatTime = totalSeconds => {
    const seconds = Math.max(0, Math.ceil(totalSeconds))
    const minutesPart = Math.floor(seconds / 60)
    const secondsPart = seconds % 60
    return `${String(minutesPart).padStart(2, "0")}:${String(secondsPart).padStart(2, "0")}`
  }

  const getRemaining = () => {
    if (timer.phase !== "running") return Number(timer.remaining_seconds) || 0
    return Math.max(0, Math.ceil((Number(timer.target_at_ms) - Date.now()) / 1000))
  }

  const emitTimer = nextTimer => {
    timer = nextTimer
    setStateValue("timer", nextTimer)
  }

  const completeTimer = () => {
    if (completedEmitted) return
    completedEmitted = true
    emitTimer({ phase: "completed", remaining_seconds: 0, target_at_ms: null })
  }

  const render = () => {
    const remaining = getRemaining()
    if (timer.phase === "running" && remaining <= 0) {
      completeTimer()
      return
    }

    const progress = Math.max(0, Math.min(1, remaining / duration))
    root.style.setProperty("--sprint-progress", `${progress * 360}deg`)
    root.classList.toggle("is-running", timer.phase === "running")
    root.classList.toggle("is-completed", timer.phase === "completed")
    time.textContent = formatTime(remaining)
    title.textContent = String(config.title || "선택한 과제")
    dial.setAttribute("aria-label", `집중시간 ${formatTime(remaining)} 남음`)

    if (timer.phase === "running") {
      status.textContent = "집중 중"
      message.textContent = "지금은 한 가지 과제에만 집중해보세요. 필요하면 언제든 멈출 수 있습니다."
      mainButton.textContent = "일시정지"
      mainButton.disabled = false
    } else if (timer.phase === "paused") {
      status.textContent = "잠시 멈춤"
      message.textContent = "흐름을 되찾을 준비가 되면 남은 시간부터 이어가세요."
      mainButton.textContent = "계속하기"
      mainButton.disabled = false
    } else if (timer.phase === "completed") {
      status.textContent = "스프린트 완주"
      message.textContent = "집중 세션을 마쳤습니다! 학습이 끝났다면 기존 과제 완료 버튼으로 기록하세요."
      mainButton.textContent = "완주 완료"
      mainButton.disabled = true
    } else {
      status.textContent = `${config.duration_minutes}분 준비`
      message.textContent = config.is_capped
        ? "긴 과제는 25분 단위로 나누어 시작합니다. 짧은 휴식 후 다시 이어가세요."
        : "준비가 되면 타이머를 시작하고 선택한 과제에 집중해보세요."
      mainButton.textContent = "집중 시작"
      mainButton.disabled = false
    }
  }

  mainButton.onclick = () => {
    if (timer.phase === "running") {
      const remaining = getRemaining()
      emitTimer({ phase: "paused", remaining_seconds: remaining, target_at_ms: null })
      return
    }
    if (timer.phase === "completed") return
    const remaining = Math.max(1, Number(timer.remaining_seconds) || duration)
    emitTimer({
      phase: "running",
      remaining_seconds: remaining,
      target_at_ms: Date.now() + remaining * 1000,
    })
  }

  resetButton.onclick = () => {
    completedEmitted = false
    emitTimer({ phase: "ready", remaining_seconds: duration, target_at_ms: null })
  }

  render()
  if (timer.phase === "running") {
    const interval = window.setInterval(render, 250)
    activeIntervals.set(parentElement, interval)
  }

  return () => {
    const interval = activeIntervals.get(parentElement)
    if (interval) window.clearInterval(interval)
    activeIntervals.delete(parentElement)
    mainButton.onclick = null
    resetButton.onclick = null
  }
}
"""


_FOCUS_SPRINT = st.components.v2.component(
    "task_focus_sprint",
    html=_FOCUS_SPRINT_HTML,
    css=_FOCUS_SPRINT_CSS,
    js=_FOCUS_SPRINT_JS,
)


def render_focus_sprint(
    task: Mapping[str, Any],
    *,
    key: str,
) -> Any:
    """선택 과제의 세션 전용 집중 타이머를 표시합니다."""

    config = build_focus_sprint_config(task)
    component_state = st.session_state.get(key)
    raw_timer = (
        component_state.get("timer")
        if isinstance(component_state, Mapping)
        else None
    )
    timer = normalize_focus_timer_state(
        raw_timer,
        duration_seconds=config["duration_seconds"],
    )
    try:
        return _FOCUS_SPRINT(
            key=key,
            data={"config": config, "timer": timer},
            height="content",
            on_timer_change=lambda: None,
        )
    except ValueError as error:
        if "Component 'task_focus_sprint' is not registered" in str(error):
            return None
        raise
