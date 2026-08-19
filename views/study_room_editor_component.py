from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st


_EDITOR_HTML = """
<div class="room-editor">
  <div class="room-toolbar">
    <span class="room-selection">가구를 클릭해 선택하세요.</span>
    <div class="room-actions">
      <button type="button" data-action="flip" disabled>좌우 반전</button>
      <button type="button" data-action="reset" disabled>배치 초기화</button>
    </div>
  </div>
  <div class="room-stage" tabindex="0" aria-label="학습방 가구 배치 편집기"></div>
  <p class="room-help">가구를 드래그해 이동하고, 모서리로 크기, 위쪽 원으로 각도를 조절하세요.</p>
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
  display: flex;
  gap: 8px;
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
  const flipButton = parentElement.querySelector('[data-action="flip"]')
  const resetButton = parentElement.querySelector('[data-action="reset"]')
  if (!editor || !stage || !selectionLabel || !flipButton || !resetButton) return

  const canvasWidth = Number(data?.canvas_width) || 1600
  const canvasHeight = Number(data?.canvas_height) || 900
  const layers = Array.isArray(data?.layers) ? data.layers : []
  let state = instances.get(parentElement)
  if (!state) {
    state = { selectedSlot: null, cleanupPointer: null, transforms: {} }
    instances.set(parentElement, state)
  }
  if (state.cleanupPointer) state.cleanupPointer()
  state.transforms = normalizeTransforms(data?.transforms, layers)
  if (!layers.some(layer => layer.slot === state.selectedSlot)) {
    state.selectedSlot = null
  }

  stage.replaceChildren()
  const baseImage = document.createElement("img")
  baseImage.className = "room-base"
  baseImage.alt = "학습방 배경"
  baseImage.src = String(data?.base_image ?? "")
  stage.appendChild(baseImage)

  const layerElements = new Map()

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

  const startPointerInteraction = (event, layer, mode) => {
    event.preventDefault()
    event.stopPropagation()
    state.selectedSlot = layer.slot
    renderAll()

    const startPoint = clientToCanvas(event)
    const startTransform = clone(state.transforms[layer.slot])
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
      emitTransforms()
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

  renderAll()

  return () => {
    if (state.cleanupPointer) state.cleanupPointer()
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
    on_transforms_change: Callable[[], None] | None = None,
) -> Any:
    """직접 조작 가능한 학습방 캔버스를 안정된 Python API로 표시합니다."""

    return _STUDY_ROOM_EDITOR(
        key=key,
        data=dict(scene),
        height="content",
        on_transforms_change=on_transforms_change,
    )
