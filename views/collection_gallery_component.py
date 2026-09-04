from collections.abc import Mapping, Sequence, Set
from typing import Any

import streamlit as st

from views.shop_asset_utils import get_approved_shop_thumbnail_data_url
from services.presentation_labels import (
    SHOP_CATEGORY_LABELS as CATEGORY_LABELS,
    SHOP_RARITY_LABELS as RARITY_LABELS,
)


MAX_COLLECTION_GALLERY_ITEMS = 30


def build_collection_gallery_items(
    items: Sequence[Mapping[str, Any]],
    *,
    owned_keys: Set[str],
    equipped_keys: Set[str],
) -> list[dict[str, Any]]:
    """카탈로그 항목을 클릭 가능한 읽기 전용 도감 데이터로 변환합니다."""

    if len(items) > MAX_COLLECTION_GALLERY_ITEMS:
        raise ValueError("컬렉션 도감에 표시할 아이템이 너무 많습니다.")

    known_keys: set[str] = set()
    gallery_items: list[dict[str, Any]] = []
    for item in items:
        item_key = _required_text(item.get("item_key"), "아이템 키")
        if item_key in known_keys:
            raise ValueError("컬렉션 도감에 중복된 아이템이 있습니다.")
        known_keys.add(item_key)

        name = _required_text(item.get("name_ko"), "아이템 이름")
        category = _required_text(item.get("category"), "카테고리")
        rarity = _required_text(item.get("rarity"), "희귀도")
        price = item.get("price")
        if (
            isinstance(price, bool)
            or not isinstance(price, int)
            or price <= 0
        ):
            raise ValueError("컬렉션 아이템 가격이 올바르지 않습니다.")
        if category not in CATEGORY_LABELS:
            raise ValueError("컬렉션 아이템 카테고리가 올바르지 않습니다.")
        if rarity not in RARITY_LABELS:
            raise ValueError("컬렉션 아이템 희귀도가 올바르지 않습니다.")

        is_owned = item_key in owned_keys
        is_equipped = item_key in equipped_keys
        if is_equipped and not is_owned:
            raise ValueError("장착한 컬렉션 아이템의 보유 정보가 올바르지 않습니다.")

        gallery_items.append(
            {
                "id": item_key,
                "name": name,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "rarity": rarity,
                "rarity_label": RARITY_LABELS[rarity],
                "price": price,
                "owned": is_owned,
                "equipped": is_equipped,
                "status": (
                    "equipped"
                    if is_equipped
                    else ("owned" if is_owned else "locked")
                ),
                "status_label": (
                    "장착 중"
                    if is_equipped
                    else ("수집 완료" if is_owned else "미수집")
                ),
                "thumbnail": get_approved_shop_thumbnail_data_url(item),
            }
        )

    return gallery_items


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"컬렉션 {field_name}가 올바르지 않습니다.")
    return value.strip()


_GALLERY_HTML = """
<section class="collection-gallery" aria-label="꾸미기 아이템 컬렉션 도감">
  <div class="collection-gallery__grid"></div>
  <aside class="collection-gallery__detail" aria-live="polite"></aside>
</section>
"""


_GALLERY_CSS = """
.collection-gallery {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(270px, 0.8fr);
  gap: 18px;
  box-sizing: border-box;
  width: 100%;
  color: var(--st-text-color);
}

.collection-gallery__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-content: start;
}

.collection-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 188px;
  flex-direction: column;
  align-items: stretch;
  overflow: hidden;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background: var(--st-secondary-background-color);
  color: var(--st-text-color);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}

.collection-card:hover {
  transform: translateY(-3px);
  border-color: var(--st-primary-color);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--st-primary-color) 15%, transparent);
}

.collection-card:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--st-primary-color) 28%, transparent);
  outline-offset: 2px;
}

.collection-card.is-selected {
  border-color: var(--st-primary-color);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--st-primary-color) 11%, transparent);
}

.collection-card[data-status="equipped"] { border-top: 4px solid var(--st-primary-color); }
.collection-card[data-rarity="rare"] { background: linear-gradient(145deg, color-mix(in srgb, #845ef7 9%, transparent), var(--st-secondary-background-color) 58%); }
.collection-card[data-rarity="uncommon"] { background: linear-gradient(145deg, color-mix(in srgb, #3978e6 7%, transparent), var(--st-secondary-background-color) 58%); }

.collection-card__visual {
  position: relative;
  display: grid;
  min-height: 116px;
  place-items: center;
  overflow: hidden;
  border-radius: 9px;
  background: color-mix(in srgb, var(--st-background-color) 80%, transparent);
}

.collection-card__visual img {
  width: 108px;
  height: 108px;
  object-fit: contain;
  transition: filter 180ms ease, transform 180ms ease;
}

.collection-card:hover .collection-card__visual img { transform: scale(1.05); }
.collection-card[data-status="locked"] .collection-card__visual img {
  filter: grayscale(1) opacity(0.34);
}

.collection-card__placeholder {
  display: grid;
  width: 82px;
  height: 82px;
  place-items: center;
  border: 2px dashed var(--st-border-color, rgba(49, 51, 63, 0.18));
  border-radius: 50%;
  font-size: 1.3rem;
  opacity: 0.55;
}

.collection-card__lock {
  position: absolute;
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--st-background-color) 90%, transparent);
  box-shadow: 0 4px 12px rgba(20, 26, 44, 0.12);
  font-size: 0.82rem;
}

.collection-card__status {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-background-color) 92%, transparent);
  color: var(--st-primary-color);
  font-size: 0.58rem;
  font-weight: 820;
}

.collection-card__name {
  margin-top: 9px;
  overflow: hidden;
  font-size: 0.76rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.collection-card__meta {
  margin-top: 3px;
  font-size: 0.62rem;
  opacity: 0.62;
}

.collection-gallery__detail {
  position: sticky;
  top: 12px;
  min-height: 430px;
  align-self: start;
  box-sizing: border-box;
  padding: 20px;
  border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.16));
  border-radius: var(--st-border-radius, 12px);
  background:
    radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--detail-color) 13%, transparent), transparent 42%),
    var(--st-secondary-background-color);
}

.collection-detail__eyebrow,
.collection-detail__name,
.collection-detail__meta,
.collection-detail__status,
.collection-detail__guide {
  margin: 0;
}

.collection-detail__eyebrow {
  color: var(--detail-color);
  font-size: 0.68rem;
  font-weight: 820;
  letter-spacing: 0.04em;
}

.collection-detail__visual {
  display: grid;
  min-height: 205px;
  margin: 12px 0 15px;
  place-items: center;
  border-radius: 12px;
  background: color-mix(in srgb, var(--st-background-color) 78%, transparent);
}

.collection-detail__visual img {
  width: 190px;
  height: 190px;
  object-fit: contain;
}

.collection-detail__visual.is-locked img { filter: grayscale(1) opacity(0.48); }
.collection-detail__name { font-size: 1.12rem; }
.collection-detail__meta { margin-top: 4px; font-size: 0.7rem; opacity: 0.66; }
.collection-detail__status {
  display: inline-flex;
  margin-top: 14px;
  padding: 5px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--detail-color) 12%, transparent);
  color: var(--detail-color);
  font-size: 0.68rem;
  font-weight: 800;
}
.collection-detail__guide {
  margin-top: 13px;
  padding: 11px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--st-background-color) 76%, transparent);
  font-size: 0.72rem;
  line-height: 1.55;
}

@media (max-width: 800px) {
  .collection-gallery { grid-template-columns: 1fr; }
  .collection-gallery__detail { position: static; min-height: auto; }
}

@media (max-width: 560px) {
  .collection-gallery__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (prefers-reduced-motion: reduce) {
  .collection-card,
  .collection-card__visual img { transition: none; }
}
"""


_GALLERY_JS = """
export default function (component) {
  const { data, parentElement } = component
  const grid = parentElement.querySelector(".collection-gallery__grid")
  const detail = parentElement.querySelector(".collection-gallery__detail")
  if (!grid || !detail) return

  const items = Array.isArray(data?.items) ? data.items : []
  let selectedId = items.find(item => item?.equipped)?.id
    || items.find(item => item?.owned)?.id
    || items[0]?.id

  const makeText = (tag, className, value) => {
    const element = document.createElement(tag)
    element.className = className
    element.textContent = String(value)
    return element
  }

  const buildVisual = (item, className) => {
    const visual = document.createElement("div")
    visual.className = className
    if (item.status === "locked") visual.classList.add("is-locked")
    if (item.thumbnail) {
      const image = document.createElement("img")
      image.src = item.thumbnail
      image.alt = item.name
      image.draggable = false
      visual.append(image)
    } else {
      visual.append(makeText("span", "collection-card__placeholder", "◇"))
    }
    return visual
  }

  const renderDetail = item => {
    detail.replaceChildren()
    if (!item) return
    detail.style.setProperty(
      "--detail-color",
      item.rarity === "rare" ? "#845ef7" : item.rarity === "uncommon" ? "#3978e6" : "var(--st-primary-color)",
    )
    const visual = buildVisual(item, "collection-detail__visual")
    const guide = item.equipped
      ? "현재 학습방에 장착되어 있습니다. 배치는 학습방 화면에서 조절할 수 있습니다."
      : item.owned
        ? "수집한 아이템입니다. 학습방 화면에서 원하는 슬롯에 장착할 수 있습니다."
        : `아직 수집하지 않은 아이템입니다. 상점에서 ${item.price} 코인으로 구매할 수 있습니다.`
    detail.append(
      makeText("p", "collection-detail__eyebrow", "컬렉션 상세"),
      visual,
      makeText("h3", "collection-detail__name", item.name),
      makeText("p", "collection-detail__meta", `${item.rarity_label} · ${item.category_label} · ${item.price} 코인`),
      makeText("p", "collection-detail__status", item.status_label),
      makeText("p", "collection-detail__guide", guide),
    )
  }

  const selectItem = item => {
    selectedId = item.id
    grid.querySelectorAll(".collection-card").forEach(card => {
      const selected = card.dataset.itemId === selectedId
      card.classList.toggle("is-selected", selected)
      card.setAttribute("aria-pressed", selected ? "true" : "false")
    })
    renderDetail(item)
  }

  grid.replaceChildren()
  items.forEach(item => {
    const card = document.createElement("button")
    card.type = "button"
    card.className = "collection-card"
    card.dataset.itemId = item.id
    card.dataset.status = item.status
    card.dataset.rarity = item.rarity
    card.setAttribute("aria-label", `${item.name}, ${item.status_label}`)
    card.setAttribute("aria-pressed", item.id === selectedId ? "true" : "false")
    if (item.id === selectedId) card.classList.add("is-selected")

    const visual = buildVisual(item, "collection-card__visual")
    if (item.status === "locked") {
      visual.append(makeText("span", "collection-card__lock", "🔒"))
    } else {
      visual.append(makeText("span", "collection-card__status", item.status_label))
    }
    card.append(
      visual,
      makeText("span", "collection-card__name", item.name),
      makeText("span", "collection-card__meta", `${item.rarity_label} · ${item.category_label}`),
    )
    card.onclick = () => selectItem(item)
    grid.append(card)
  })

  renderDetail(items.find(item => item.id === selectedId))
  return () => {
    grid.querySelectorAll("button").forEach(button => { button.onclick = null })
  }
}
"""


_COLLECTION_GALLERY = st.components.v2.component(
    "interactive_collection_gallery",
    html=_GALLERY_HTML,
    css=_GALLERY_CSS,
    js=_GALLERY_JS,
)


def render_collection_gallery(
    items: Sequence[Mapping[str, Any]],
    *,
    key: str,
) -> bool:
    """인터랙티브 도감을 표시하고 미지원 테스트 환경 여부를 반환합니다."""

    try:
        _COLLECTION_GALLERY(
            key=key,
            data={"items": [dict(item) for item in items]},
            height="content",
        )
        return True
    except ValueError as error:
        if "Component 'interactive_collection_gallery' is not registered" in str(
            error
        ):
            return False
        raise
