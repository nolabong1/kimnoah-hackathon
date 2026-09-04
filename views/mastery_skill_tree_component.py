from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import streamlit as st

from services.time_service import SEOUL_TIMEZONE


MAX_SKILL_TREE_NODES = 15


def build_mastery_skill_tree_nodes(
    masteries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """숙련도 데이터를 결정론적인 추천 보완 경로 노드로 변환합니다."""

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for mastery in masteries:
        concept_id = mastery.get("concept_id")
        concept_name = mastery.get("concept_name")
        mastery_score = mastery.get("mastery_score")
        is_weak = mastery.get("is_weak")

        if not isinstance(concept_id, str) or not concept_id.strip():
            raise ValueError("스킬트리 개념 ID가 올바르지 않습니다.")
        if concept_id in seen_ids:
            raise ValueError("스킬트리에 중복된 개념이 있습니다.")
        if not isinstance(concept_name, str) or not concept_name.strip():
            raise ValueError("스킬트리 개념 이름이 올바르지 않습니다.")
        if (
            isinstance(mastery_score, bool)
            or not isinstance(mastery_score, int)
            or not 0 <= mastery_score <= 100
        ):
            raise ValueError("스킬트리 숙련도 점수가 올바르지 않습니다.")
        if not isinstance(is_weak, bool):
            raise ValueError("스킬트리 취약 상태가 올바르지 않습니다.")

        seen_ids.add(concept_id)
        normalized.append(
            {
                "id": concept_id,
                "name": concept_name.strip(),
                "score": mastery_score,
                "is_weak": is_weak,
                "correct_count": _non_negative_count(
                    mastery.get("correct_count"),
                    "누적 정답 수",
                ),
                "incorrect_count": _non_negative_count(
                    mastery.get("incorrect_count"),
                    "누적 오답 수",
                ),
                "consecutive_incorrect_count": _non_negative_count(
                    mastery.get("consecutive_incorrect_count"),
                    "연속 오답 수",
                ),
                "last_answer_correct": mastery.get("last_answer_correct"),
                "last_assessed_at": _format_last_assessed_at(
                    mastery.get("last_assessed_at")
                ),
            }
        )

    normalized.sort(
        key=lambda node: (
            not node["is_weak"],
            node["score"],
            -node["consecutive_incorrect_count"],
            node["name"].casefold(),
        )
    )
    visible_nodes = normalized[:MAX_SKILL_TREE_NODES]

    for rank, node in enumerate(visible_nodes, start=1):
        node["rank"] = rank
        node["recommended"] = rank == 1
        node["status"] = "review" if node["is_weak"] else "steady"
        node["status_label"] = (
            "복습 필요" if node["is_weak"] else "기준 이상"
        )
        node["last_answer_label"] = _last_answer_label(
            node["last_answer_correct"]
        )

    return visible_nodes


def _non_negative_count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"스킬트리 {field_name}가 올바르지 않습니다.")
    return value


def _format_last_assessed_at(value: object) -> str:
    if value is None:
        return "평가 기록 없음"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("스킬트리 최근 평가 시각이 올바르지 않습니다.")

    try:
        assessed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("스킬트리 최근 평가 시각이 올바르지 않습니다.") from None

    if assessed_at.tzinfo is None:
        assessed_at = assessed_at.replace(tzinfo=SEOUL_TIMEZONE)
    return assessed_at.astimezone(SEOUL_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def _last_answer_label(value: object) -> str:
    if value is True:
        return "최근 정답"
    if value is False:
        return "최근 오답"
    if value is None:
        return "최근 응답 없음"
    raise ValueError("스킬트리 최근 정답 상태가 올바르지 않습니다.")


_SKILL_TREE_HTML = """
<section class="skill-tree" aria-label="개념 숙련도 스킬트리">
  <header class="skill-tree__header">
    <div>
      <p class="skill-tree__eyebrow">추천 보완 경로</p>
      <h3 class="skill-tree__title">개념 숙련도 스킬트리</h3>
      <p class="skill-tree__description">
        취약 상태와 숙련도 점수를 기준으로 먼저 살펴볼 개념을 정렬했습니다.
      </p>
    </div>
    <div class="skill-tree__legend" aria-label="노드 상태 범례">
      <span><i class="is-review"></i>복습 필요</span>
      <span><i class="is-steady"></i>취약 기준 이상</span>
    </div>
  </header>
  <div class="skill-tree__layout">
    <div class="skill-tree__path" role="list"></div>
    <aside class="skill-tree__detail" aria-live="polite">
      <p class="skill-tree__detail-eyebrow">선택한 개념</p>
      <div class="skill-tree__detail-content"></div>
    </aside>
  </div>
  <p class="skill-tree__notice"></p>
</section>
"""


_SKILL_TREE_CSS = """
.skill-tree {
  box-sizing: border-box;
  width: 100%;
  padding: 20px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background:
    radial-gradient(circle at 10% 0%, color-mix(in srgb, var(--st-primary-color) 10%, transparent), transparent 35%),
    var(--st-secondary-background-color);
  color: var(--st-text-color);
}

.skill-tree__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.skill-tree__eyebrow,
.skill-tree__title,
.skill-tree__description,
.skill-tree__detail-eyebrow,
.skill-tree__notice {
  margin: 0;
}

.skill-tree__eyebrow,
.skill-tree__detail-eyebrow {
  color: var(--st-primary-color);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.skill-tree__title {
  margin-top: 3px;
  font-size: 1.05rem;
  line-height: 1.4;
}

.skill-tree__description {
  margin-top: 5px;
  font-size: 0.76rem;
  line-height: 1.5;
  opacity: 0.68;
}

.skill-tree__legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px 13px;
  font-size: 0.69rem;
  opacity: 0.76;
}

.skill-tree__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.skill-tree__legend i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.skill-tree__legend .is-review { background: #ef6b73; }
.skill-tree__legend .is-steady { background: #43a884; }

.skill-tree__layout {
  display: grid;
  grid-template-columns: minmax(300px, 1.35fr) minmax(250px, 0.9fr);
  gap: 18px;
  align-items: stretch;
}

.skill-tree__path {
  position: relative;
  display: flex;
  max-height: 520px;
  min-height: 350px;
  overflow-y: auto;
  flex-direction: column;
  gap: 14px;
  padding: 8px 16px 8px 8px;
  scrollbar-width: thin;
}

.skill-tree__path::before {
  position: absolute;
  top: 28px;
  bottom: 28px;
  left: 50%;
  width: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-primary-color) 24%, var(--st-border-color));
  content: "";
  transform: translateX(-50%);
}

.skill-node-row {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
}

.skill-node-row:nth-child(odd) { justify-content: flex-start; padding-right: 45%; }
.skill-node-row:nth-child(even) { justify-content: flex-end; padding-left: 45%; }

.skill-node {
  position: relative;
  display: grid;
  width: 100%;
  min-width: 170px;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  gap: 9px;
  align-items: center;
  box-sizing: border-box;
  padding: 10px 11px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: 11px;
  background: var(--st-background-color);
  color: var(--st-text-color);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
}

.skill-node::after {
  position: absolute;
  top: 50%;
  width: 22px;
  height: 2px;
  background: color-mix(in srgb, var(--st-primary-color) 28%, var(--st-border-color));
  content: "";
}

.skill-node-row:nth-child(odd) .skill-node::after { right: -22px; }
.skill-node-row:nth-child(even) .skill-node::after { left: -22px; }

.skill-node:hover {
  transform: translateY(-2px);
  border-color: var(--st-primary-color);
  box-shadow: 0 8px 20px color-mix(in srgb, var(--st-primary-color) 16%, transparent);
}

.skill-node:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--st-primary-color) 28%, transparent);
  outline-offset: 2px;
}

.skill-node.is-selected {
  border-color: var(--st-primary-color);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--st-primary-color) 12%, transparent);
}

.skill-node.is-review { border-left: 4px solid #ef6b73; }
.skill-node.is-steady { border-left: 4px solid #43a884; }

.skill-node__rank {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--st-primary-color) 12%, transparent);
  color: var(--st-primary-color);
  font-size: 0.72rem;
  font-weight: 850;
}

.skill-node__text { min-width: 0; }
.skill-node__name {
  display: block;
  overflow: hidden;
  font-size: 0.78rem;
  font-weight: 780;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-node__status {
  display: block;
  margin-top: 2px;
  font-size: 0.64rem;
  opacity: 0.62;
}

.skill-node__score {
  font-size: 0.77rem;
  font-weight: 820;
}

.skill-node__recommended {
  position: absolute;
  top: -8px;
  right: 8px;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--st-primary-color);
  color: white;
  font-size: 0.58rem;
  font-weight: 800;
}

.skill-tree__detail {
  min-height: 350px;
  box-sizing: border-box;
  padding: 18px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.14));
  border-radius: 12px;
  background: var(--st-background-color);
}

.skill-detail__name { margin: 7px 0 3px; font-size: 1.15rem; }
.skill-detail__status { margin: 0 0 18px; font-size: 0.72rem; opacity: 0.68; }
.skill-detail__score-row { display: flex; align-items: baseline; justify-content: space-between; }
.skill-detail__score-row strong { font-size: 1.65rem; }
.skill-detail__score-row span { font-size: 0.7rem; opacity: 0.62; }
.skill-detail__track {
  width: 100%;
  height: 9px;
  margin: 8px 0 18px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-text-color) 10%, transparent);
}
.skill-detail__fill { display: block; height: 100%; border-radius: inherit; background: var(--st-primary-color); }
.skill-detail__metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }
.skill-detail__metric { padding: 10px 8px; border-radius: 9px; background: var(--st-secondary-background-color); text-align: center; }
.skill-detail__metric strong { display: block; font-size: 0.92rem; }
.skill-detail__metric span { display: block; margin-top: 3px; font-size: 0.6rem; opacity: 0.62; }
.skill-detail__meta { margin: 16px 0 0; font-size: 0.7rem; line-height: 1.6; opacity: 0.7; }
.skill-detail__guide { margin: 15px 0 0; padding: 11px; border-radius: 9px; background: color-mix(in srgb, var(--st-primary-color) 9%, transparent); font-size: 0.72rem; line-height: 1.55; }

.skill-tree__notice {
  margin-top: 14px;
  font-size: 0.67rem;
  line-height: 1.5;
  opacity: 0.6;
}

@media (max-width: 760px) {
  .skill-tree__header { flex-direction: column; }
  .skill-tree__legend { justify-content: flex-start; }
  .skill-tree__layout { grid-template-columns: 1fr; }
  .skill-tree__path { max-height: 430px; }
  .skill-tree__detail { min-height: auto; }
}

@media (prefers-reduced-motion: reduce) {
  .skill-node { transition: none; }
}
"""


_SKILL_TREE_JS = """
export default function (component) {
  const { data, parentElement } = component
  const path = parentElement.querySelector(".skill-tree__path")
  const detail = parentElement.querySelector(".skill-tree__detail-content")
  const notice = parentElement.querySelector(".skill-tree__notice")
  if (!path || !detail || !notice) return

  const nodes = Array.isArray(data?.nodes) ? data.nodes : []
  const totalCount = Number(data?.total_count) || nodes.length
  let selectedId = nodes.find(node => node?.recommended)?.id || nodes[0]?.id

  const makeText = (tag, className, value) => {
    const element = document.createElement(tag)
    element.className = className
    element.textContent = String(value)
    return element
  }

  const renderDetail = node => {
    detail.replaceChildren()
    if (!node) return

    const title = makeText("h4", "skill-detail__name", node.name)
    const status = makeText(
      "p",
      "skill-detail__status",
      `${node.status_label} · 보완 우선순위 ${node.rank}`,
    )
    const scoreRow = document.createElement("div")
    scoreRow.className = "skill-detail__score-row"
    scoreRow.append(
      makeText("strong", "", node.score),
      makeText("span", "", "현재 숙련도 / 100"),
    )
    const track = document.createElement("div")
    track.className = "skill-detail__track"
    track.setAttribute("role", "progressbar")
    track.setAttribute("aria-valuemin", "0")
    track.setAttribute("aria-valuemax", "100")
    track.setAttribute("aria-valuenow", String(node.score))
    const fill = document.createElement("span")
    fill.className = "skill-detail__fill"
    fill.style.width = `${Math.max(0, Math.min(100, Number(node.score) || 0))}%`
    track.append(fill)

    const metrics = document.createElement("div")
    metrics.className = "skill-detail__metrics"
    ;[
      [node.correct_count, "누적 정답"],
      [node.incorrect_count, "누적 오답"],
      [node.consecutive_incorrect_count, "연속 오답"],
    ].forEach(([value, label]) => {
      const metric = document.createElement("div")
      metric.className = "skill-detail__metric"
      metric.append(
        makeText("strong", "", value),
        makeText("span", "", label),
      )
      metrics.append(metric)
    })

    const meta = makeText(
      "p",
      "skill-detail__meta",
      `${node.last_answer_label}\n최근 평가 · ${node.last_assessed_at}`,
    )
    meta.style.whiteSpace = "pre-line"
    const guide = makeText(
      "p",
      "skill-detail__guide",
      node.is_weak
        ? "자동 복습 과제와 연결된 퀴즈 해설부터 다시 확인해보세요."
        : "현재 취약 기준 이상입니다. 다음 개념으로 이동하거나 가볍게 인출 연습해보세요.",
    )
    detail.append(title, status, scoreRow, track, metrics, meta, guide)
  }

  const selectNode = node => {
    selectedId = node.id
    path.querySelectorAll(".skill-node").forEach(button => {
      const selected = button.dataset.nodeId === selectedId
      button.classList.toggle("is-selected", selected)
      button.setAttribute("aria-pressed", selected ? "true" : "false")
    })
    renderDetail(node)
  }

  path.replaceChildren()
  nodes.forEach(node => {
    const row = document.createElement("div")
    row.className = "skill-node-row"
    row.setAttribute("role", "listitem")

    const button = document.createElement("button")
    button.type = "button"
    button.className = `skill-node is-${node.status}`
    button.dataset.nodeId = node.id
    button.setAttribute("aria-label", `${node.name}, 숙련도 ${node.score}점, ${node.status_label}`)
    button.setAttribute("aria-pressed", node.id === selectedId ? "true" : "false")
    if (node.id === selectedId) button.classList.add("is-selected")

    const text = document.createElement("span")
    text.className = "skill-node__text"
    text.append(
      makeText("span", "skill-node__name", node.name),
      makeText("span", "skill-node__status", node.status_label),
    )
    button.append(
      makeText("span", "skill-node__rank", node.rank),
      text,
      makeText("span", "skill-node__score", `${node.score}점`),
    )
    if (node.recommended) {
      button.append(makeText("span", "skill-node__recommended", "먼저 보기"))
    }
    button.onclick = () => selectNode(node)
    row.append(button)
    path.append(row)
  })

  renderDetail(nodes.find(node => node.id === selectedId))
  const hiddenCount = Math.max(0, totalCount - nodes.length)
  notice.textContent = hiddenCount > 0
    ? `화면 가독성을 위해 우선순위가 높은 15개를 표시합니다. 나머지 ${hiddenCount}개는 개념 카드에서 확인할 수 있습니다. 이 연결선은 선수 관계가 아닌 추천 복습 순서입니다.`
    : "연결선은 선수 개념 관계가 아니라 현재 기록에 따른 추천 복습 순서입니다. 노드를 선택해 판단 근거를 확인하세요."

  return () => {
    path.querySelectorAll("button").forEach(button => { button.onclick = null })
  }
}
"""


_MASTERY_SKILL_TREE = st.components.v2.component(
    "mastery_skill_tree",
    html=_SKILL_TREE_HTML,
    css=_SKILL_TREE_CSS,
    js=_SKILL_TREE_JS,
)


def render_mastery_skill_tree(
    nodes: Sequence[Mapping[str, Any]],
    *,
    total_count: int,
    key: str,
) -> Any:
    """클릭 가능한 숙련도 스킬트리를 표시합니다."""

    try:
        return _MASTERY_SKILL_TREE(
            key=key,
            data={
                "nodes": [dict(node) for node in nodes],
                "total_count": total_count,
            },
            height="content",
        )
    except ValueError as error:
        if "Component 'mastery_skill_tree' is not registered" in str(error):
            return None
        raise
