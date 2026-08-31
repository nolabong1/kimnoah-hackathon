from collections.abc import Sequence
from typing import Any

import streamlit as st


_FEEDBACK_HTML = """
<div class="celebration-overlay" hidden aria-live="polite" aria-atomic="true">
  <div class="celebration-card" data-tone="success">
    <div class="particle-layer" aria-hidden="true"></div>
    <div class="celebration-icon" aria-hidden="true"></div>
    <p class="celebration-title"></p>
    <p class="celebration-value"></p>
    <p class="celebration-message"></p>
    <div class="celebration-progress" aria-hidden="true"><span></span></div>
    <button type="button" class="celebration-skip" aria-label="축하 연출 건너뛰기">
      건너뛰기
    </button>
  </div>
</div>
"""

_FEEDBACK_CSS = """
.celebration-overlay {
  align-items: flex-start;
  display: flex;
  inset: 0;
  justify-content: center;
  padding-top: 24px;
  pointer-events: none;
  position: fixed;
  z-index: 999999;
}

.celebration-overlay[hidden] { display: none; }

.celebration-overlay[data-placement="inline"] {
  align-items: stretch;
  inset: auto;
  padding: 0 0 12px;
  position: relative;
  width: 100%;
  z-index: auto;
}

.celebration-card {
  --tone: var(--st-primary-color);
  background: color-mix(in srgb, var(--st-background-color) 94%, var(--tone));
  border: 1px solid color-mix(in srgb, var(--tone) 44%, transparent);
  border-radius: calc(var(--st-base-radius, 12px) * 1.35);
  box-shadow: 0 18px 48px color-mix(in srgb, var(--tone) 24%, transparent);
  color: var(--st-text-color);
  font-family: var(--st-font);
  max-width: min(420px, calc(100vw - 32px));
  min-width: min(360px, calc(100vw - 32px));
  overflow: hidden;
  padding: 22px 24px 16px;
  pointer-events: auto;
  position: relative;
  text-align: center;
  transform-origin: top center;
}

.celebration-card[data-tone="success"] { --tone: var(--st-green-color, #25a56a); }
.celebration-card[data-tone="bonus"] { --tone: var(--st-yellow-color, #f1b928); }
.celebration-card[data-tone="quiz"] { --tone: var(--st-blue-color, #3978e6); }
.celebration-card[data-tone="achievement"] { --tone: var(--st-violet-color, #845ef7); }
.celebration-card[data-tone="challenge"] { --tone: var(--st-orange-color, #e78b24); }

.celebration-overlay[data-placement="inline"] .celebration-card {
  box-shadow: 0 8px 24px color-mix(in srgb, var(--tone) 16%, transparent);
  max-width: none;
  min-width: 0;
  width: 100%;
}

.celebration-card.is-entering { animation: card-enter 460ms cubic-bezier(.18,.85,.32,1.18); }
.celebration-card.is-leaving { animation: card-leave 260ms ease-in forwards; }

.celebration-icon {
  align-items: center;
  background: color-mix(in srgb, var(--tone) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--tone) 45%, transparent);
  border-radius: 999px;
  color: var(--tone);
  display: inline-flex;
  font-size: 26px;
  font-weight: 800;
  height: 54px;
  justify-content: center;
  width: 54px;
}

.celebration-title { font-size: 1.08rem; font-weight: 750; margin: 10px 0 0; }
.celebration-value { color: var(--tone); font-size: 1.75rem; font-weight: 850; margin: 2px 0; }
.celebration-message { font-size: .88rem; margin: 2px 0 14px; opacity: .76; }

.celebration-progress {
  background: color-mix(in srgb, var(--tone) 14%, transparent);
  border-radius: 999px;
  height: 4px;
  overflow: hidden;
}

.celebration-progress span {
  background: var(--tone);
  display: block;
  height: 100%;
  transform-origin: left;
  width: 100%;
}

.celebration-card.is-entering .celebration-progress span {
  animation: progress-drain var(--event-duration, 2200ms) linear forwards;
}

.celebration-skip {
  background: transparent;
  border: 0;
  color: var(--st-text-color);
  cursor: pointer;
  font: inherit;
  font-size: .76rem;
  margin-top: 9px;
  opacity: .55;
  padding: 2px 8px;
}

.particle-layer { inset: 0; overflow: visible; pointer-events: none; position: absolute; }
.particle {
  --distance: 112px;
  background: var(--tone);
  border-radius: 2px;
  height: 8px;
  left: 50%;
  opacity: 0;
  position: absolute;
  top: 28px;
  width: 5px;
}
.celebration-card.is-entering .particle {
  animation: particle-burst 720ms ease-out var(--delay) both;
}

@keyframes card-enter {
  0% { opacity: 0; transform: translateY(-24px) scale(.9); }
  70% { opacity: 1; transform: translateY(3px) scale(1.02); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes card-leave {
  to { opacity: 0; transform: translateY(-14px) scale(.96); }
}
@keyframes progress-drain { from { transform: scaleX(1); } to { transform: scaleX(0); } }
@keyframes particle-burst {
  0% { opacity: 0; transform: rotate(var(--angle)) translateY(0) scale(.5); }
  22% { opacity: 1; }
  100% { opacity: 0; transform: rotate(var(--angle)) translateY(calc(-1 * var(--distance))) scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .celebration-card.is-entering, .celebration-card.is-leaving,
  .celebration-card.is-entering .particle,
  .celebration-card.is-entering .celebration-progress span { animation: none; }
}
"""

_FEEDBACK_JS = """
export default function (component) {
  const { data, parentElement } = component
  const overlay = parentElement.querySelector(".celebration-overlay")
  const card = parentElement.querySelector(".celebration-card")
  const icon = parentElement.querySelector(".celebration-icon")
  const title = parentElement.querySelector(".celebration-title")
  const value = parentElement.querySelector(".celebration-value")
  const message = parentElement.querySelector(".celebration-message")
  const particles = parentElement.querySelector(".particle-layer")
  const skip = parentElement.querySelector(".celebration-skip")
  if (!overlay || !card || !icon || !title || !value || !message || !particles || !skip) return

  const events = Array.isArray(data?.events) ? data.events : []
  const placement = data?.placement === "inline" ? "inline" : "overlay"
  overlay.dataset.placement = placement
  const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false
  const eventDuration = reducedMotion ? 1100 : 2300
  const leaveDuration = reducedMotion ? 0 : 260
  let index = 0
  let disposed = false
  let eventTimer = null
  let nextTimer = null

  const clearTimers = () => {
    if (eventTimer !== null) globalThis.clearTimeout(eventTimer)
    if (nextTimer !== null) globalThis.clearTimeout(nextTimer)
    eventTimer = null
    nextTimer = null
  }

  const finish = () => {
    clearTimers()
    overlay.hidden = true
    card.classList.remove("is-entering", "is-leaving")
  }

  const createParticles = () => {
    particles.replaceChildren()
    if (reducedMotion) return
    for (let particleIndex = 0; particleIndex < 16; particleIndex += 1) {
      const particle = document.createElement("span")
      particle.className = "particle"
      particle.style.setProperty("--angle", `${particleIndex * 22.5}deg`)
      particle.style.setProperty("--delay", `${(particleIndex % 4) * 34}ms`)
      particle.style.setProperty("--distance", `${92 + (particleIndex % 3) * 18}px`)
      particles.appendChild(particle)
    }
  }

  const showCurrent = () => {
    if (disposed || index >= events.length) {
      finish()
      return
    }
    const event = events[index] ?? {}
    card.dataset.tone = String(event.tone ?? "success")
    icon.textContent = String(event.icon ?? "✓")
    title.textContent = String(event.title ?? "학습 기록 완료")
    value.textContent = String(event.value ?? "")
    message.textContent = String(event.message ?? "")
    card.style.setProperty("--event-duration", `${eventDuration}ms`)
    createParticles()
    overlay.hidden = false
    card.classList.remove("is-entering", "is-leaving")
    void card.offsetWidth
    card.classList.add("is-entering")

    eventTimer = globalThis.setTimeout(() => {
      card.classList.remove("is-entering")
      card.classList.add("is-leaving")
      nextTimer = globalThis.setTimeout(() => {
        index += 1
        showCurrent()
      }, leaveDuration)
    }, eventDuration)
  }

  skip.onclick = finish
  if (events.length > 0) showCurrent()
  else finish()

  return () => {
    disposed = true
    skip.onclick = null
    finish()
  }
}
"""


_INTERACTION_FEEDBACK = st.components.v2.component(
    "learning_interaction_feedback",
    html=_FEEDBACK_HTML,
    css=_FEEDBACK_CSS,
    js=_FEEDBACK_JS,
)


def render_interaction_feedback_component(
    events: Sequence[dict[str, Any]],
    *,
    key: str,
    placement: str = "overlay",
) -> Any:
    """검증된 학습 이벤트를 화면 위에서 순서대로 한 번 재생합니다."""

    return _INTERACTION_FEEDBACK(
        key=key,
        data={
            "events": [dict(event) for event in events],
            "placement": "inline" if placement == "inline" else "overlay",
        },
        height="content" if placement == "inline" else 1,
    )
