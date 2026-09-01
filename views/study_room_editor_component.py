from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from views.streak_presentation import (
    get_streak_tier_label,
    resolve_streak_tier,
)


def build_study_room_mood(
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """프로필의 레벨·연속 학습일을 읽기 전용 학습방 분위기로 변환합니다."""

    level = profile.get("level")
    current_streak = profile.get("current_streak")
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("학습방 레벨 정보가 올바르지 않습니다.")
    if (
        isinstance(current_streak, bool)
        or not isinstance(current_streak, int)
        or current_streak < 0
    ):
        raise ValueError("학습방 연속 학습일 정보가 올바르지 않습니다.")

    tier = resolve_streak_tier(current_streak)
    if tier == "legendary":
        title = f"{current_streak}일의 학습 리듬"
        message = "한 달의 꾸준함이 공간을 채웠어요. 오늘도 무리 없이 이어가세요."
    elif tier == "blazing":
        title = f"{current_streak}일 연속 몰입 중"
        message = "두 주의 리듬이 선명해졌어요. 익숙한 시간에 한 과제를 시작해보세요."
    elif tier == "strong":
        title = f"{current_streak}일 연속 집중 중"
        message = "꾸준한 리듬이 이어지고 있어요. 오늘도 한 과제씩 완성해보세요."
    elif tier == "growing":
        title = f"{current_streak}일째 학습 불꽃"
        message = "학습 흐름이 자라고 있어요. 지금의 속도를 안정적으로 이어가세요."
    elif tier == "spark":
        title = f"{current_streak}일 연속 학습"
        message = "학습 불씨가 켜졌어요. 오늘의 작은 진전을 이어가보세요."
    else:
        title = "오늘의 학습 준비 완료"
        message = "첫 과제를 완료하면 학습 불씨와 연속 기록이 시작됩니다."

    return {
        "level": level,
        "current_streak": current_streak,
        "tier": tier,
        "tier_label": get_streak_tier_label(tier),
        "title": title,
        "message": message,
        "character": {
            "name": "공부 고양이",
            "messages": _character_messages(tier, current_streak),
            "save_message": "새 배치를 기억했어요. 이 공간에서 다시 힘내봐요!",
        },
    }


def _character_messages(tier: str, current_streak: int) -> list[str]:
    """연속 학습 상태에 맞는 짧은 캐릭터 반응을 결정론적으로 만듭니다."""

    messages_by_tier = {
        "legendary": [
            f"{current_streak}일의 선택이 큰 리듬이 됐어요. 오늘은 가볍게 이어가요!",
            "오래 이어온 만큼 어려운 날에는 분량을 줄여도 괜찮아요.",
            "한 달의 기록보다 중요한 건 오늘 다시 자리에 앉는 일이에요.",
        ],
        "blazing": [
            f"{current_streak}일째예요. 두 주 동안 만든 리듬을 오늘도 지켜봐요!",
            "집중이 흐려지면 가장 짧은 복습 과제부터 시작해봐요.",
            "꾸준한 시간대와 시작 신호를 정해두면 내일도 더 쉬워져요.",
        ],
        "strong": [
            f"{current_streak}일의 리듬이 단단해요. 오늘도 한 걸음만 이어가요!",
            "어려운 과제는 작은 단계로 나누면 훨씬 가벼워져요.",
            "꾸준함이 이미 실력이 되고 있어요. 지금 속도를 지켜봐요.",
        ],
        "growing": [
            f"{current_streak}일째 불꽃이 자라고 있어요. 오늘도 같이 집중해요!",
            "완벽하게 하려 하기보다, 오늘 할 한 과제부터 시작해봐요.",
            "짧게 복습하고 새 내용을 배우면 기억이 더 오래가요.",
        ],
        "spark": [
            "학습 불씨가 켜졌어요. 가장 쉬운 과제부터 시작해볼까요?",
            "막히면 알고 있는 것과 모르는 것을 한 줄씩 나눠 적어봐요.",
            "오늘의 작은 완료가 내일의 시작을 더 쉽게 만들어요.",
        ],
        "ready": [
            "첫 과제를 시작하면 오늘의 학습 불씨가 켜져요!",
            "5분만 해보자는 마음으로 가장 작은 단계부터 시작해봐요.",
            "준비는 끝났어요. 오늘 배우고 싶은 한 가지를 골라봐요.",
        ],
    }
    return messages_by_tier[tier]


_EDITOR_HTML = """
<div class="room-editor">
  <div class="room-toolbar">
    <span class="room-selection">가구를 클릭해 선택하세요.</span>
    <div class="room-actions">
      <span class="room-mood" aria-label="학습방 현재 분위기"></span>
      <button type="button" data-action="encourage">응원 받기</button>
      <button type="button" data-action="flip" disabled>좌우 반전</button>
      <button type="button" data-action="reset" disabled>배치 초기화</button>
    </div>
  </div>
  <div class="room-stage" tabindex="0" aria-label="학습방 가구 배치 편집기"></div>
  <p class="room-help">
    가구를 드래그해 이동하고, 모서리로 크기, 위쪽 원으로 각도를 조절하세요.
    <span class="room-character-help" hidden>공부 고양이는 가볍게 클릭하면 반응합니다.</span>
  </p>
</div>
"""

_EDITOR_CSS = """
.room-editor {
  color: var(--st-text-color);
  font-family: var(--st-font);
  width: 100%;
}

.room-toolbar {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 10px;
  min-height: 36px;
}

.room-selection {
  font-size: 0.9rem;
  font-weight: 600;
}

.room-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.room-mood {
  background: color-mix(in srgb, var(--st-primary-color) 11%, transparent);
  border-radius: 999px;
  color: var(--st-primary-color);
  font-size: 0.72rem;
  font-weight: 750;
  padding: 6px 9px;
}

.room-actions button {
  background: var(--st-secondary-background-color);
  border: 1px solid color-mix(in srgb, var(--st-text-color) 18%, transparent);
  border-radius: var(--st-button-border-radius, 8px);
  color: var(--st-text-color);
  cursor: pointer;
  font: inherit;
  font-size: 0.82rem;
  min-height: 32px;
  padding: 5px 10px;
}

.room-actions button:disabled {
  cursor: default;
  opacity: 0.45;
}

.room-actions button:not(:disabled):hover {
  border-color: var(--st-primary-color);
  color: var(--st-primary-color);
}

.room-stage {
  --room-aura-opacity: .34;
  --room-aura-size: 55%;
  --room-spark-size: 7px;
  aspect-ratio: 16 / 9;
  background: var(--st-secondary-background-color);
  border: 1px solid color-mix(in srgb, var(--st-text-color) 14%, transparent);
  border-radius: 12px;
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
  touch-action: none;
  user-select: none;
  width: 100%;
}

.room-stage::after {
  background: radial-gradient(
    circle at 50% 20%,
    color-mix(in srgb, var(--room-mood-color, var(--st-primary-color)) 18%, transparent),
    transparent var(--room-aura-size)
  );
  content: "";
  inset: 0;
  opacity: var(--room-aura-opacity);
  pointer-events: none;
  position: absolute;
  transition: opacity 280ms ease;
  z-index: 80;
}

.room-stage[data-mood="ready"] { --room-mood-color: #a7afc2; --room-aura-opacity: .18; }
.room-stage[data-mood="spark"] { --room-mood-color: var(--st-orange-color, #ff9f43); --room-aura-opacity: .3; }
.room-stage[data-mood="growing"] { --room-mood-color: #ff7438; --room-aura-opacity: .44; }
.room-stage[data-mood="strong"] { --room-mood-color: var(--st-red-color, #f44771); --room-aura-opacity: .58; --room-aura-size: 63%; --room-spark-size: 8px; }
.room-stage[data-mood="blazing"] { --room-mood-color: #e63973; --room-aura-opacity: .74; --room-aura-size: 70%; --room-spark-size: 9px; }
.room-stage[data-mood="legendary"] { --room-mood-color: var(--st-violet-color, #7b61ff); --room-aura-opacity: .9; --room-aura-size: 78%; --room-spark-size: 10px; }
.room-stage[data-mood="blazing"],
.room-stage[data-mood="legendary"] {
  border-color: color-mix(in srgb, var(--room-mood-color) 46%, transparent);
  box-shadow: 0 12px 34px color-mix(in srgb, var(--room-mood-color) 18%, transparent);
}
.room-stage.is-celebrating::after { opacity: 1; }

.room-reaction {
  background: color-mix(in srgb, var(--st-background-color) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--room-mood-color) 35%, transparent);
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(20, 26, 44, 0.15);
  box-sizing: border-box;
  color: var(--st-text-color);
  left: 50%;
  max-width: min(76%, 520px);
  opacity: 0;
  padding: 10px 14px;
  pointer-events: none;
  position: absolute;
  text-align: center;
  top: 8%;
  transform: translate(-50%, -8px);
  transition: opacity 180ms ease, transform 220ms ease;
  z-index: 100;
}

.room-reaction strong { display: block; font-size: 0.82rem; }
.room-reaction span { display: block; font-size: 0.69rem; margin-top: 3px; opacity: 0.72; }
.room-reaction.is-visible { opacity: 1; transform: translate(-50%, 0); }

.room-character-reaction {
  background: color-mix(in srgb, var(--st-background-color) 95%, transparent);
  border: 1px solid color-mix(in srgb, var(--room-mood-color) 42%, transparent);
  border-radius: 13px;
  box-shadow: 0 9px 24px rgba(20, 26, 44, 0.16);
  box-sizing: border-box;
  color: var(--st-text-color);
  max-width: min(43%, 300px);
  opacity: 0;
  padding: 8px 11px;
  pointer-events: none;
  position: absolute;
  text-align: left;
  transform: translate(-50%, 6px) scale(.96);
  transition: opacity 160ms ease, transform 210ms ease;
  z-index: 110;
}

.room-character-reaction::after {
  background: inherit;
  border-bottom: 1px solid color-mix(in srgb, var(--room-mood-color) 42%, transparent);
  border-right: 1px solid color-mix(in srgb, var(--room-mood-color) 42%, transparent);
  bottom: -6px;
  content: "";
  height: 10px;
  left: calc(50% - 5px);
  position: absolute;
  transform: rotate(45deg);
  width: 10px;
}

.room-character-reaction strong { display: block; font-size: .72rem; }
.room-character-reaction span { display: block; font-size: .65rem; line-height: 1.45; margin-top: 2px; opacity: .78; }
.room-character-reaction.is-visible { opacity: 1; transform: translate(-50%, 0) scale(1); }

.room-save-feedback {
  align-items: center;
  background: color-mix(in srgb, var(--st-background-color) 94%, transparent);
  border: 1px solid color-mix(in srgb, var(--st-primary-color) 45%, transparent);
  border-radius: 999px;
  bottom: 6%;
  box-shadow: 0 10px 28px rgba(20, 26, 44, 0.18);
  display: flex;
  gap: 10px;
  left: 50%;
  max-width: 82%;
  opacity: 0;
  padding: 9px 14px;
  pointer-events: none;
  position: absolute;
  transform: translate(-50%, 10px) scale(.96);
  transition: opacity 180ms ease, transform 240ms ease;
  z-index: 105;
}

.room-save-feedback__icon {
  align-items: center;
  background: var(--st-primary-color);
  border-radius: 50%;
  color: var(--st-button-primary-text-color, #fff);
  display: inline-flex;
  flex: 0 0 24px;
  font-size: .78rem;
  height: 24px;
  justify-content: center;
  width: 24px;
}

.room-save-feedback__copy { min-width: 0; }
.room-save-feedback strong { display: block; font-size: .78rem; }
.room-save-feedback span { display: block; font-size: .66rem; margin-top: 2px; opacity: .72; }
.room-save-feedback.is-visible { opacity: 1; transform: translate(-50%, 0) scale(1); }
.room-stage.is-saved { animation: room-save-pulse 780ms ease-out; }

.room-spark {
  animation: room-spark 1.15s ease-out forwards;
  background: var(--room-mood-color);
  border-radius: 50%;
  height: var(--room-spark-size);
  left: var(--spark-x);
  pointer-events: none;
  position: absolute;
  top: var(--spark-y);
  width: var(--room-spark-size);
  z-index: 95;
}

.room-stage.is-celebrating .room-object > img {
  animation: room-object-glow 900ms ease-in-out 2 alternate;
}

.room-base {
  height: 100%;
  inset: 0;
  object-fit: contain;
  pointer-events: none;
  position: absolute;
  width: 100%;
}

.room-object {
  cursor: grab;
  position: absolute;
  transform-origin: center;
}

.room-object:active {
  cursor: grabbing;
}

.room-object > img {
  height: 100%;
  pointer-events: none;
  width: 100%;
}

.room-object.is-character:not(.is-selected) > img {
  animation: room-character-breathe 2.8s ease-in-out infinite;
}

.room-stage[data-mood="strong"] .room-object.is-character:not(.is-selected) > img { animation-duration: 2.35s; }
.room-stage[data-mood="blazing"] .room-object.is-character:not(.is-selected) > img { animation-duration: 1.85s; filter: drop-shadow(0 5px 8px color-mix(in srgb, var(--room-mood-color) 35%, transparent)); }
.room-stage[data-mood="legendary"] .room-object.is-character:not(.is-selected) > img { animation-duration: 1.45s; filter: drop-shadow(0 7px 12px color-mix(in srgb, var(--room-mood-color) 48%, transparent)); }

.room-object.is-character.is-reacting > img {
  animation: room-character-hop 560ms ease-out;
}

.room-object.is-selected {
  outline: 3px solid var(--st-primary-color);
  outline-offset: 2px;
}

.room-handle {
  background: white;
  border: 3px solid var(--st-primary-color);
  border-radius: 50%;
  box-sizing: border-box;
  height: 16px;
  position: absolute;
  width: 16px;
  z-index: 2;
}

.room-handle[data-handle="nw"] { cursor: nwse-resize; left: -10px; top: -10px; }
.room-handle[data-handle="ne"] { cursor: nesw-resize; right: -10px; top: -10px; }
.room-handle[data-handle="sw"] { bottom: -10px; cursor: nesw-resize; left: -10px; }
.room-handle[data-handle="se"] { bottom: -10px; cursor: nwse-resize; right: -10px; }

.room-rotation-line {
  background: var(--st-primary-color);
  height: 28px;
  left: calc(50% - 1px);
  position: absolute;
  top: -31px;
  width: 2px;
}

.room-handle[data-handle="rotate"] {
  cursor: grab;
  left: calc(50% - 9px);
  top: -48px;
  height: 18px;
  width: 18px;
}

.room-help {
  color: color-mix(in srgb, var(--st-text-color) 65%, transparent);
  font-size: 0.78rem;
  margin: 8px 2px 0;
}

.room-character-help { display: inline; margin-left: 4px; }

@keyframes room-spark {
  from { opacity: 0; transform: translateY(10px) scale(0.4); }
  35% { opacity: 0.95; }
  to { opacity: 0; transform: translateY(-32px) scale(1.15); }
}

@keyframes room-object-glow {
  from { filter: drop-shadow(0 0 0 transparent); }
  to { filter: drop-shadow(0 7px 9px color-mix(in srgb, var(--room-mood-color) 38%, transparent)); }
}

@keyframes room-save-pulse {
  0% { border-color: var(--st-primary-color); box-shadow: 0 0 0 0 color-mix(in srgb, var(--st-primary-color) 38%, transparent); }
  55% { box-shadow: 0 0 0 9px color-mix(in srgb, var(--st-primary-color) 0%, transparent); }
  100% { border-color: color-mix(in srgb, var(--st-text-color) 14%, transparent); box-shadow: none; }
}

@keyframes room-character-breathe {
  0%, 100% { transform: scaleX(var(--room-character-flip, 1)) translateY(0); }
  50% { transform: scaleX(var(--room-character-flip, 1)) translateY(-3px); }
}

@keyframes room-character-hop {
  0%, 100% { transform: scaleX(var(--room-character-flip, 1)) translateY(0) scale(1); }
  42% { transform: scaleX(var(--room-character-flip, 1)) translateY(-12px) scale(1.04); }
}

@media (max-width: 720px) {
  .room-toolbar { align-items: flex-start; flex-direction: column; }
  .room-actions { justify-content: flex-start; }
}

@media (prefers-reduced-motion: reduce) {
  .room-stage::after,
  .room-reaction,
  .room-character-reaction,
  .room-save-feedback { transition: none; }
  .room-spark,
  .room-object.is-character:not(.is-selected) > img,
  .room-object.is-character.is-reacting > img,
  .room-stage.is-celebrating .room-object > img,
  .room-stage.is-saved { animation: none; }
}
"""

_EDITOR_JS = """
const instances = new WeakMap()

const LIMITS = {
  x: [-800, 800],
  y: [-450, 450],
  scale: [25, 200],
  rotation: [-180, 180],
}

const defaultTransform = () => ({
  x: 0,
  y: 0,
  scale: 100,
  rotation: 0,
  flip_horizontal: false,
})

const clamp = (value, minimum, maximum) => (
  Math.min(maximum, Math.max(minimum, value))
)

const normalizeRotation = value => {
  let normalized = value
  while (normalized > 180) normalized -= 360
  while (normalized < -180) normalized += 360
  return Math.round(normalized)
}

const clone = value => JSON.parse(JSON.stringify(value ?? {}))

function normalizeTransforms(rawTransforms, layers) {
  const source = clone(rawTransforms)
  const normalized = {}
  for (const layer of layers) {
    const raw = source[layer.slot] ?? {}
    normalized[layer.slot] = {
      x: clamp(Math.round(Number(raw.x) || 0), ...LIMITS.x),
      y: clamp(Math.round(Number(raw.y) || 0), ...LIMITS.y),
      scale: clamp(Math.round(Number(raw.scale) || 100), ...LIMITS.scale),
      rotation: clamp(
        normalizeRotation(Number(raw.rotation) || 0),
        ...LIMITS.rotation,
      ),
      flip_horizontal: raw.flip_horizontal === true,
    }
  }
  return normalized
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const editor = parentElement.querySelector(".room-editor")
  const stage = parentElement.querySelector(".room-stage")
  const selectionLabel = parentElement.querySelector(".room-selection")
  const moodLabel = parentElement.querySelector(".room-mood")
  const characterHelp = parentElement.querySelector(".room-character-help")
  const encourageButton = parentElement.querySelector('[data-action="encourage"]')
  const flipButton = parentElement.querySelector('[data-action="flip"]')
  const resetButton = parentElement.querySelector('[data-action="reset"]')
  if (!editor || !stage || !selectionLabel || !moodLabel || !characterHelp || !encourageButton || !flipButton || !resetButton) return

  const canvasWidth = Number(data?.canvas_width) || 1600
  const canvasHeight = Number(data?.canvas_height) || 900
  const layers = Array.isArray(data?.layers) ? data.layers : []
  let state = instances.get(parentElement)
  if (!state) {
    state = {
      selectedSlot: null,
      cleanupPointer: null,
      transforms: {},
      reactionTimer: null,
      characterReactionTimer: null,
      characterMessageIndex: 0,
      saveFeedbackTimer: null,
      lastSaveEventId: null,
      saveFeedbackVisibleUntil: 0,
    }
    instances.set(parentElement, state)
  }
  if (state.cleanupPointer) state.cleanupPointer()
  state.transforms = normalizeTransforms(data?.transforms, layers)
  if (!layers.some(layer => layer.slot === state.selectedSlot)) {
    state.selectedSlot = null
  }

  stage.replaceChildren()
  const mood = data?.mood && typeof data.mood === "object"
    ? data.mood
    : {
        tier: "ready",
        title: "오늘의 학습 준비 완료",
        message: "학습을 시작할 준비가 됐어요.",
        level: 1,
        current_streak: 0,
      }
  stage.dataset.mood = String(mood.tier || "ready")
  const tierLabel = String(mood.tier_label || "불씨 준비")
  moodLabel.textContent = `Lv.${Number(mood.level) || 1} · ${tierLabel} · ${Number(mood.current_streak) || 0}일`

  const baseImage = document.createElement("img")
  baseImage.className = "room-base"
  baseImage.alt = "학습방 배경"
  baseImage.src = String(data?.base_image ?? "")
  stage.appendChild(baseImage)

  const reaction = document.createElement("div")
  reaction.className = "room-reaction"
  reaction.setAttribute("role", "status")
  reaction.append(
    Object.assign(document.createElement("strong"), { textContent: String(mood.title || "학습 응원") }),
    Object.assign(document.createElement("span"), { textContent: String(mood.message || "오늘도 한 단계씩 진행해보세요.") }),
  )
  stage.appendChild(reaction)

  const characterReaction = document.createElement("div")
  characterReaction.className = "room-character-reaction"
  characterReaction.setAttribute("role", "status")
  characterReaction.setAttribute("aria-live", "polite")
  const characterReactionTitle = document.createElement("strong")
  const characterReactionMessage = document.createElement("span")
  characterReaction.append(characterReactionTitle, characterReactionMessage)
  stage.appendChild(characterReaction)

  const saveFeedback = document.createElement("div")
  saveFeedback.className = "room-save-feedback"
  saveFeedback.setAttribute("role", "status")
  const saveFeedbackIcon = document.createElement("span")
  saveFeedbackIcon.className = "room-save-feedback__icon"
  saveFeedbackIcon.textContent = "✓"
  const saveFeedbackCopy = document.createElement("span")
  saveFeedbackCopy.className = "room-save-feedback__copy"
  const saveFeedbackTitle = document.createElement("strong")
  const saveFeedbackMessage = document.createElement("span")
  saveFeedbackCopy.append(saveFeedbackTitle, saveFeedbackMessage)
  saveFeedback.append(saveFeedbackIcon, saveFeedbackCopy)
  stage.appendChild(saveFeedback)

  const layerElements = new Map()
  const characterLayer = layers.find(
    layer => layer.item_key === "accent_study_cat" && layer.slot === "accent",
  )
  characterHelp.hidden = !characterLayer

  const emitTransforms = () => {
    setStateValue("transforms", clone(state.transforms))
  }

  const clientToCanvas = event => {
    const rect = stage.getBoundingClientRect()
    return {
      x: (event.clientX - rect.left) * canvasWidth / rect.width,
      y: (event.clientY - rect.top) * canvasHeight / rect.height,
    }
  }

  const layerCenter = layer => {
    const transform = state.transforms[layer.slot]
    return {
      x: Number(layer.base_x) + Number(layer.width) / 2 + transform.x,
      y: Number(layer.base_y) + Number(layer.height) / 2 + transform.y,
    }
  }

  const renderToolbar = () => {
    const selected = layers.find(layer => layer.slot === state.selectedSlot)
    selectionLabel.textContent = selected
      ? `${selected.label} 선택됨`
      : "가구를 클릭해 선택하세요."
    flipButton.disabled = !selected
    resetButton.disabled = !selected
  }

  const renderLayer = layer => {
    const element = layerElements.get(layer.slot)
    if (!element) return
    const transform = state.transforms[layer.slot]
    const center = layerCenter(layer)
    const scaleRatio = transform.scale / 100
    element.style.left = `${center.x / canvasWidth * 100}%`
    element.style.top = `${center.y / canvasHeight * 100}%`
    element.style.width = `${Number(layer.width) * scaleRatio / canvasWidth * 100}%`
    element.style.height = `${Number(layer.height) * scaleRatio / canvasHeight * 100}%`
    element.style.transform = `translate(-50%, -50%) rotate(${transform.rotation}deg)`
    element.classList.toggle("is-selected", layer.slot === state.selectedSlot)
    const image = element.querySelector("img")
    image.style.setProperty(
      "--room-character-flip",
      transform.flip_horizontal ? "-1" : "1",
    )
    image.style.transform = transform.flip_horizontal ? "scaleX(-1)" : "none"
    const controls = element.querySelectorAll(".room-control")
    controls.forEach(control => {
      control.hidden = layer.slot !== state.selectedSlot
    })
  }

  const renderAll = () => {
    for (const layer of layers) renderLayer(layer)
    renderToolbar()
  }

  const revealCharacterReaction = reason => {
    if (!characterLayer) return
    const character = mood?.character && typeof mood.character === "object"
      ? mood.character
      : {}
    const messages = Array.isArray(character.messages)
      ? character.messages.filter(message => typeof message === "string" && message.trim())
      : []
    let message = "오늘도 한 단계씩 같이 해봐요!"
    if (reason === "save" && typeof character.save_message === "string") {
      message = character.save_message
    } else if (messages.length) {
      message = messages[state.characterMessageIndex % messages.length]
      state.characterMessageIndex += 1
    }

    const center = layerCenter(characterLayer)
    const transform = state.transforms[characterLayer.slot]
    const halfHeight = Number(characterLayer.height) * transform.scale / 200
    const reactionX = clamp(center.x, canvasWidth * .14, canvasWidth * .86)
    const reactionY = clamp(
      center.y - halfHeight - 34,
      canvasHeight * .08,
      canvasHeight * .82,
    )
    characterReaction.style.left = `${reactionX / canvasWidth * 100}%`
    characterReaction.style.top = `${reactionY / canvasHeight * 100}%`
    characterReactionTitle.textContent = String(character.name || "공부 고양이")
    characterReactionMessage.textContent = message

    const characterElement = layerElements.get(characterLayer.slot)
    if (state.characterReactionTimer) window.clearTimeout(state.characterReactionTimer)
    characterReaction.classList.remove("is-visible")
    characterElement?.classList.remove("is-reacting")
    void characterReaction.offsetWidth
    characterReaction.classList.add("is-visible")
    characterElement?.classList.add("is-reacting")
    state.characterReactionTimer = window.setTimeout(() => {
      characterReaction.classList.remove("is-visible")
      characterElement?.classList.remove("is-reacting")
      state.characterReactionTimer = null
    }, 2800)
  }

  const startPointerInteraction = (event, layer, mode) => {
    event.preventDefault()
    event.stopPropagation()
    state.selectedSlot = layer.slot
    renderAll()

    const startPoint = clientToCanvas(event)
    const startTransform = clone(state.transforms[layer.slot])
    let maximumPointerDistance = 0
    const center = layerCenter(layer)
    const startDistance = Math.max(
      1,
      Math.hypot(startPoint.x - center.x, startPoint.y - center.y),
    )
    const startAngle = Math.atan2(
      startPoint.y - center.y,
      startPoint.x - center.x,
    )

    const onMove = moveEvent => {
      const point = clientToCanvas(moveEvent)
      maximumPointerDistance = Math.max(
        maximumPointerDistance,
        Math.hypot(point.x - startPoint.x, point.y - startPoint.y),
      )
      const next = state.transforms[layer.slot]
      if (mode === "move") {
        next.x = clamp(
          Math.round(startTransform.x + point.x - startPoint.x),
          ...LIMITS.x,
        )
        next.y = clamp(
          Math.round(startTransform.y + point.y - startPoint.y),
          ...LIMITS.y,
        )
      } else if (mode === "scale") {
        const distance = Math.hypot(point.x - center.x, point.y - center.y)
        next.scale = clamp(
          Math.round(startTransform.scale * distance / startDistance),
          ...LIMITS.scale,
        )
      } else if (mode === "rotate") {
        const angle = Math.atan2(point.y - center.y, point.x - center.x)
        const deltaDegrees = (angle - startAngle) * 180 / Math.PI
        next.rotation = normalizeRotation(startTransform.rotation + deltaDegrees)
      }
      renderLayer(layer)
    }

    const finish = () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", finish)
      window.removeEventListener("pointercancel", finish)
      state.cleanupPointer = null
      const isCharacterTap = (
        mode === "move"
        && layer.item_key === "accent_study_cat"
        && maximumPointerDistance <= 12
      )
      if (isCharacterTap) {
        state.transforms[layer.slot] = startTransform
        renderLayer(layer)
        revealCharacterReaction("tap")
      } else {
        emitTransforms()
      }
    }

    state.cleanupPointer = () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", finish)
      window.removeEventListener("pointercancel", finish)
      state.cleanupPointer = null
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", finish, { once: true })
    window.addEventListener("pointercancel", finish, { once: true })
  }

  for (const [index, layer] of layers.entries()) {
    const element = document.createElement("div")
    element.className = "room-object"
    element.classList.toggle("is-character", layer.item_key === "accent_study_cat")
    element.dataset.slot = layer.slot
    element.style.zIndex = String(20 + index)
    element.setAttribute("role", "button")
    element.setAttribute("aria-label", `${layer.label} 이동 및 크기 조절`)

    const image = document.createElement("img")
    image.alt = layer.label
    image.draggable = false
    image.src = layer.source
    element.appendChild(image)

    for (const handleName of ["nw", "ne", "sw", "se"]) {
      const handle = document.createElement("span")
      handle.className = "room-handle room-control"
      handle.dataset.handle = handleName
      handle.hidden = true
      handle.onpointerdown = event => startPointerInteraction(event, layer, "scale")
      element.appendChild(handle)
    }

    const rotationLine = document.createElement("span")
    rotationLine.className = "room-rotation-line room-control"
    rotationLine.hidden = true
    element.appendChild(rotationLine)

    const rotationHandle = document.createElement("span")
    rotationHandle.className = "room-handle room-control"
    rotationHandle.dataset.handle = "rotate"
    rotationHandle.hidden = true
    rotationHandle.onpointerdown = event => startPointerInteraction(event, layer, "rotate")
    element.appendChild(rotationHandle)

    element.onpointerdown = event => {
      if (event.target instanceof HTMLElement && event.target.dataset.handle) return
      startPointerInteraction(event, layer, "move")
    }
    layerElements.set(layer.slot, element)
    stage.appendChild(element)
  }

  stage.onpointerdown = event => {
    if (event.target === stage || event.target === baseImage) {
      state.selectedSlot = null
      renderAll()
    }
  }

  flipButton.onclick = () => {
    if (!state.selectedSlot) return
    const transform = state.transforms[state.selectedSlot]
    transform.flip_horizontal = !transform.flip_horizontal
    renderAll()
    emitTransforms()
  }

  resetButton.onclick = () => {
    if (!state.selectedSlot) return
    state.transforms[state.selectedSlot] = defaultTransform()
    renderAll()
    emitTransforms()
  }

  encourageButton.onclick = () => {
    if (state.reactionTimer) window.clearTimeout(state.reactionTimer)
    stage.querySelectorAll(".room-spark").forEach(spark => spark.remove())
    stage.classList.remove("is-celebrating")
    void stage.offsetWidth
    stage.classList.add("is-celebrating")
    reaction.classList.add("is-visible")

    const sparkCounts = {
      ready: 4,
      spark: 7,
      growing: 10,
      strong: 12,
      blazing: 18,
      legendary: 24,
    }
    const sparkCount = sparkCounts[String(mood.tier || "ready")] || 4
    for (let index = 0; index < sparkCount; index += 1) {
      const spark = document.createElement("span")
      spark.className = "room-spark"
      spark.style.setProperty("--spark-x", `${12 + (index * 37) % 76}%`)
      spark.style.setProperty("--spark-y", `${24 + (index * 23) % 58}%`)
      spark.style.animationDelay = `${(index % 4) * 80}ms`
      stage.appendChild(spark)
    }

    state.reactionTimer = window.setTimeout(() => {
      reaction.classList.remove("is-visible")
      stage.classList.remove("is-celebrating")
      stage.querySelectorAll(".room-spark").forEach(spark => spark.remove())
      state.reactionTimer = null
    }, 3200)
  }

  const revealSaveFeedback = () => {
    const feedback = data?.save_feedback
    if (!feedback || typeof feedback !== "object") return
    const eventId = String(feedback.event_id || "")
    if (!eventId) return
    const now = Date.now()
    const isNewEvent = eventId !== state.lastSaveEventId
    if (isNewEvent) {
      state.lastSaveEventId = eventId
      state.saveFeedbackVisibleUntil = now + 2800
    } else if (now >= state.saveFeedbackVisibleUntil) {
      return
    }
    saveFeedbackTitle.textContent = String(feedback.title || "학습방 저장 완료")
    saveFeedbackMessage.textContent = String(feedback.message || "현재 구성을 안전하게 저장했습니다.")
    if (state.saveFeedbackTimer) window.clearTimeout(state.saveFeedbackTimer)
    if (isNewEvent) {
      stage.classList.remove("is-saved")
      void stage.offsetWidth
      stage.classList.add("is-saved")
      revealCharacterReaction("save")
    }
    saveFeedback.classList.add("is-visible")
    state.saveFeedbackTimer = window.setTimeout(() => {
      saveFeedback.classList.remove("is-visible")
      stage.classList.remove("is-saved")
      state.saveFeedbackTimer = null
    }, Math.max(0, state.saveFeedbackVisibleUntil - now))
  }

  renderAll()
  revealSaveFeedback()

  return () => {
    if (state.cleanupPointer) state.cleanupPointer()
    if (state.reactionTimer) window.clearTimeout(state.reactionTimer)
    if (state.characterReactionTimer) window.clearTimeout(state.characterReactionTimer)
    if (state.saveFeedbackTimer) window.clearTimeout(state.saveFeedbackTimer)
    encourageButton.onclick = null
    flipButton.onclick = null
    resetButton.onclick = null
  }
}
"""


_STUDY_ROOM_EDITOR = st.components.v2.component(
    "study_room_direct_editor",
    html=_EDITOR_HTML,
    css=_EDITOR_CSS,
    js=_EDITOR_JS,
)


def render_study_room_editor(
    scene: Mapping[str, Any],
    *,
    key: str,
    mood: Mapping[str, Any] | None = None,
    save_feedback: Mapping[str, Any] | None = None,
    on_transforms_change: Callable[[], None] | None = None,
) -> Any:
    """직접 조작 가능한 학습방 캔버스를 안정된 Python API로 표시합니다."""

    return _STUDY_ROOM_EDITOR(
        key=key,
        data={
            **dict(scene),
            "mood": dict(mood or {}),
            "save_feedback": dict(save_feedback or {}),
        },
        height="content",
        on_transforms_change=on_transforms_change,
    )
