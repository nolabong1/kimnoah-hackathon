from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

import streamlit as st


_TASK_TYPE_LABELS = {
    "learn": "학습",
    "review": "복습",
    "quiz": "퀴즈",
}


def build_learning_quest_nodes(
    tasks: Sequence[Mapping[str, Any]],
    selected_task_id: str,
) -> list[dict[str, Any]]:
    """오늘 과제를 표시 순서가 보존된 퀘스트 노드로 변환합니다."""

    nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, task in enumerate(tasks, start=1):
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("퀘스트 맵 과제 ID가 올바르지 않습니다.")
        if task_id in seen_ids:
            raise ValueError("퀘스트 맵에 중복된 과제가 있습니다.")
        seen_ids.add(task_id)

        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("퀘스트 맵 과제 제목이 올바르지 않습니다.")

        task_type = str(task.get("task_type", ""))
        estimated_minutes = task.get("estimated_minutes")
        if not isinstance(estimated_minutes, int) or estimated_minutes < 0:
            raise ValueError("퀘스트 맵 예상 학습시간이 올바르지 않습니다.")

        nodes.append(
            {
                "id": task_id,
                "step": index,
                "title": title.strip(),
                "task_type": task_type,
                "task_type_label": _TASK_TYPE_LABELS.get(task_type, "과제"),
                "estimated_minutes": estimated_minutes,
                "completed": task.get("status") == "completed",
                "selected": task_id == selected_task_id,
            }
        )

    if nodes and selected_task_id not in seen_ids:
        raise ValueError("선택한 과제가 오늘 퀘스트에 없습니다.")

    return nodes


def apply_quest_map_selection(
    state: MutableMapping[str, Any],
    *,
    component_key: str,
    selection_key: str,
    allowed_task_ids: Sequence[str],
) -> bool:
    """컴포넌트가 보낸 과제 ID를 허용목록 검증 후 선택 상태에 반영합니다."""

    component_state = state.get(component_key)
    if not isinstance(component_state, Mapping):
        return False

    selected_task_id = component_state.get("selected_task_id")
    allowed_ids = set(allowed_task_ids)
    if not isinstance(selected_task_id, str) or selected_task_id not in allowed_ids:
        return False

    if state.get(selection_key) == selected_task_id:
        return False

    state[selection_key] = selected_task_id
    return True


_QUEST_MAP_HTML = """
<section class="quest-map" aria-label="오늘 학습 퀘스트 맵">
  <div class="quest-map__summary">
    <div>
      <p class="quest-map__eyebrow">오늘의 학습 여정</p>
      <h3 class="quest-map__title">과제를 따라 한 단계씩 진행해보세요</h3>
    </div>
    <span class="quest-map__progress"></span>
  </div>
  <div class="quest-map__rail" role="list"></div>
</section>
"""


_QUEST_MAP_CSS = """
.quest-map {
  box-sizing: border-box;
  width: 100%;
  padding: 18px 20px 16px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background:
    radial-gradient(circle at 8% 0%, color-mix(in srgb, var(--st-primary-color) 10%, transparent), transparent 32%),
    var(--st-secondary-background-color);
  color: var(--st-text-color);
  overflow: hidden;
}

.quest-map__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.quest-map__eyebrow {
  margin: 0 0 3px;
  color: var(--st-primary-color);
  font-size: 0.75rem;
  font-weight: 750;
  letter-spacing: 0.04em;
}

.quest-map__title {
  margin: 0;
  font-size: 1rem;
  line-height: 1.4;
}

.quest-map__progress {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-primary-color) 12%, transparent);
  color: var(--st-primary-color);
  font-size: 0.78rem;
  font-weight: 750;
}

.quest-map__rail {
  display: flex;
  align-items: flex-start;
  min-width: max-content;
  overflow-x: auto;
  padding: 3px 3px 8px;
  scrollbar-width: thin;
}

.quest-step {
  position: relative;
  display: flex;
  flex: 1 0 132px;
  min-width: 132px;
  max-width: 190px;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.quest-step:not(:last-child)::after {
  content: "";
  position: absolute;
  z-index: 0;
  top: 21px;
  left: calc(50% + 24px);
  width: calc(100% - 48px);
  height: 4px;
  border-radius: 999px;
  background: var(--st-border-color, rgba(49, 51, 63, 0.16));
}

.quest-step.is-path-complete:not(:last-child)::after {
  background: var(--st-primary-color);
}

.quest-step__node {
  position: relative;
  z-index: 1;
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  box-sizing: border-box;
  border: 2px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
  border-radius: 50%;
  background: var(--st-background-color);
  color: var(--st-text-color);
  font: inherit;
  font-size: 0.86rem;
  font-weight: 800;
}

button.quest-step__node {
  cursor: pointer;
  transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
}

button.quest-step__node:hover {
  transform: translateY(-2px);
  border-color: var(--st-primary-color);
  box-shadow: 0 7px 18px color-mix(in srgb, var(--st-primary-color) 22%, transparent);
}

button.quest-step__node:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--st-primary-color) 30%, transparent);
  outline-offset: 3px;
}

.quest-step.is-complete .quest-step__node,
.quest-step.is-finish.is-complete .quest-step__node {
  border-color: var(--st-primary-color);
  background: var(--st-primary-color);
  color: white;
}

.quest-step.is-selected .quest-step__node {
  border-color: var(--st-primary-color);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--st-primary-color) 14%, transparent);
}

.quest-step.is-selected:not(.is-complete) .quest-step__node {
  color: var(--st-primary-color);
}

.quest-step__label {
  width: 118px;
  margin-top: 9px;
  overflow: hidden;
  color: var(--st-text-color);
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quest-step__meta {
  margin-top: 3px;
  color: var(--st-text-color);
  font-size: 0.7rem;
  opacity: 0.64;
}

.quest-step__current {
  min-height: 18px;
  margin-top: 4px;
  color: var(--st-primary-color);
  font-size: 0.67rem;
  font-weight: 750;
}

@media (max-width: 700px) {
  .quest-map {
    padding-inline: 14px;
  }

  .quest-map__summary {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  button.quest-step__node {
    transition: none;
  }
}
"""


_QUEST_MAP_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector(".quest-map")
  const rail = parentElement.querySelector(".quest-map__rail")
  const progress = parentElement.querySelector(".quest-map__progress")
  if (!root || !rail || !progress) return

  const nodes = Array.isArray(data?.nodes) ? data.nodes : []
  const completedCount = nodes.filter(node => node?.completed === true).length
  const allComplete = nodes.length > 0 && completedCount === nodes.length
  progress.textContent = `${completedCount}/${nodes.length} 완료`
  rail.replaceChildren()

  const makeText = (className, text) => {
    const element = document.createElement("span")
    element.className = className
    element.textContent = text
    return element
  }

  const appendStep = ({ kind, label, meta, complete, pathComplete, task }) => {
    const step = document.createElement("div")
    step.className = "quest-step"
    step.setAttribute("role", "listitem")
    if (kind) step.classList.add(`is-${kind}`)
    if (complete) step.classList.add("is-complete")
    if (pathComplete) step.classList.add("is-path-complete")
    if (task?.selected) step.classList.add("is-selected")

    const node = document.createElement(task ? "button" : "span")
    node.className = "quest-step__node"
    node.textContent = complete ? "✓" : kind === "start" ? "S" : kind === "finish" ? "★" : String(task.step)

    if (task) {
      node.type = "button"
      node.setAttribute("aria-label", `${task.step}단계 ${task.title}, ${task.completed ? "완료" : "대기"}`)
      if (task.selected) node.setAttribute("aria-current", "step")
      node.onclick = () => setTriggerValue("selected_task_id", task.id)
    } else {
      node.setAttribute("aria-hidden", "true")
    }

    step.append(node)
    step.append(makeText("quest-step__label", label))
    step.append(makeText("quest-step__meta", meta))
    step.append(makeText("quest-step__current", task?.selected ? "지금 보고 있어요" : ""))
    rail.append(step)
  }

  appendStep({
    kind: "start",
    label: "시작",
    meta: "오늘의 여정",
    complete: true,
    pathComplete: true,
  })

  nodes.forEach(task => {
    appendStep({
      kind: "task",
      label: task.title,
      meta: `${task.task_type_label} · ${task.estimated_minutes}분`,
      complete: task.completed === true,
      pathComplete: task.completed === true,
      task,
    })
  })

  appendStep({
    kind: "finish",
    label: "완료",
    meta: allComplete ? "오늘 학습 완료" : "모든 과제 완료 후 도착",
    complete: allComplete,
    pathComplete: false,
  })

  return () => {
    rail.querySelectorAll("button").forEach(button => {
      button.onclick = null
    })
  }
}
"""


_LEARNING_QUEST_MAP = st.components.v2.component(
    "learning_quest_map",
    html=_QUEST_MAP_HTML,
    css=_QUEST_MAP_CSS,
    js=_QUEST_MAP_JS,
)


def render_learning_quest_map(
    nodes: Sequence[Mapping[str, Any]],
    *,
    key: str,
    on_selected_task_id_change: Callable[[], None] | None = None,
) -> Any:
    """오늘 과제 여정을 클릭 가능한 퀘스트 맵으로 표시합니다."""

    try:
        return _LEARNING_QUEST_MAP(
            key=key,
            data={"nodes": [dict(node) for node in nodes]},
            height="content",
            on_selected_task_id_change=on_selected_task_id_change,
        )
    except ValueError as error:
        if "Component 'learning_quest_map' is not registered" in str(error):
            return None
        raise
