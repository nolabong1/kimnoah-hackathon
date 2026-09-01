from collections.abc import Mapping
from typing import Any

import streamlit as st

from views.shop_asset_utils import get_approved_shop_thumbnail_data_url


CATEGORY_LABELS = {
    "background": "배경",
    "floor": "바닥",
    "desk": "책상",
    "chair": "의자",
    "decoration": "장식",
    "accent": "포인트",
}
RARITY_LABELS = {
    "common": "일반",
    "uncommon": "고급",
    "rare": "희귀",
}


def build_shop_purchase_feedback(
    item: Mapping[str, Any],
    purchase_result: Mapping[str, Any],
) -> dict[str, Any]:
    """검증된 구매 결과와 카탈로그 항목을 한 번 표시할 payload로 묶습니다."""

    item_key = _required_text(item.get("item_key"), "아이템 키")
    result_item_key = _required_text(
        purchase_result.get("item_key"),
        "구매 결과 아이템 키",
    )
    if result_item_key != item_key:
        raise RuntimeError("구매 결과의 아이템 정보가 요청과 일치하지 않습니다.")

    item_price = _positive_int(item.get("price"), "아이템 가격")
    result_price = _positive_int(
        purchase_result.get("price"),
        "구매 결과 가격",
    )
    if result_price != item_price:
        raise RuntimeError("구매 결과의 가격이 상점 카탈로그와 일치하지 않습니다.")

    already_owned = purchase_result.get("already_owned")
    if not isinstance(already_owned, bool):
        raise ValueError("구매 결과의 중복 보유 상태가 올바르지 않습니다.")
    balance = _non_negative_int(
        purchase_result.get("balance"),
        "구매 후 코인",
    )
    coins_spent = _non_negative_int(
        purchase_result.get("coins_spent"),
        "사용 코인",
    )
    expected_spent = 0 if already_owned else item_price
    if coins_spent != expected_spent:
        raise RuntimeError("구매 결과의 코인 사용량이 올바르지 않습니다.")

    category = _required_text(item.get("category"), "카테고리")
    rarity = _required_text(item.get("rarity"), "희귀도")
    if category not in CATEGORY_LABELS or rarity not in RARITY_LABELS:
        raise ValueError("구매 아이템 표시 정보가 올바르지 않습니다.")

    item_name = _required_text(item.get("name_ko"), "아이템 이름")
    newly_purchased = not already_owned
    message = (
        "이미 보유한 아이템입니다. 코인은 차감되지 않았습니다."
        if already_owned
        else (
            f"'{item_name}' 구매를 완료했습니다. "
            f"남은 코인은 {balance}개입니다."
        )
    )
    return {
        "item_key": item_key,
        "item_name": item_name,
        "category_label": CATEGORY_LABELS[category],
        "rarity": rarity,
        "rarity_label": RARITY_LABELS[rarity],
        "price": item_price,
        "coins_spent": coins_spent,
        "balance": balance,
        "newly_purchased": newly_purchased,
        "message": message,
        "thumbnail": get_approved_shop_thumbnail_data_url(item),
    }


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value.strip()


def _positive_int(value: object, field_name: str) -> int:
    normalized = _non_negative_int(value, field_name)
    if normalized == 0:
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return normalized


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} 정보가 올바르지 않습니다.")
    return value


_PURCHASE_REVEAL_HTML = """
<section class="purchase-reveal" aria-live="polite">
  <div class="purchase-reveal__shine" aria-hidden="true"></div>
  <div class="purchase-reveal__visual"></div>
  <div class="purchase-reveal__content">
    <p class="purchase-reveal__eyebrow">새 아이템 획득</p>
    <h3 class="purchase-reveal__name"></h3>
    <p class="purchase-reveal__meta"></p>
    <div class="purchase-reveal__coins">
      <span class="purchase-reveal__spent"></span>
      <span class="purchase-reveal__balance"></span>
    </div>
    <p class="purchase-reveal__guide">내 아이템에 영구 보관되며 학습방에서 장착할 수 있습니다.</p>
  </div>
</section>
"""


_PURCHASE_REVEAL_CSS = """
.purchase-reveal {
  --reveal-color: var(--st-primary-color);
  position: relative;
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 22px;
  align-items: center;
  overflow: hidden;
  box-sizing: border-box;
  width: 100%;
  margin-bottom: 16px;
  padding: 20px 24px;
  border: 1px solid color-mix(in srgb, var(--reveal-color) 36%, var(--st-border-color));
  border-radius: var(--st-border-radius, 12px);
  background:
    radial-gradient(circle at 12% 20%, color-mix(in srgb, var(--reveal-color) 18%, transparent), transparent 36%),
    var(--st-secondary-background-color);
  color: var(--st-text-color);
  animation: purchase-reveal-enter 440ms cubic-bezier(.18,.84,.3,1.12) both;
}

.purchase-reveal[data-rarity="uncommon"] { --reveal-color: #3978e6; }
.purchase-reveal[data-rarity="rare"] { --reveal-color: #845ef7; }

.purchase-reveal__shine {
  position: absolute;
  top: -60%;
  left: -25%;
  width: 18%;
  height: 220%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.5), transparent);
  pointer-events: none;
  transform: rotate(18deg);
  animation: purchase-reveal-shine 1.05s ease 180ms both;
}

.purchase-reveal__visual {
  display: grid;
  min-height: 160px;
  place-items: center;
  border-radius: 12px;
  background: color-mix(in srgb, var(--st-background-color) 78%, transparent);
}

.purchase-reveal__visual img {
  width: 150px;
  height: 150px;
  object-fit: contain;
  filter: drop-shadow(0 10px 14px color-mix(in srgb, var(--reveal-color) 24%, transparent));
  animation: purchase-item-arrive 620ms cubic-bezier(.2,.9,.32,1.18) 100ms both;
}

.purchase-reveal__placeholder {
  display: grid;
  width: 105px;
  height: 105px;
  place-items: center;
  border: 2px dashed color-mix(in srgb, var(--reveal-color) 42%, transparent);
  border-radius: 50%;
  color: var(--reveal-color);
  font-size: 1.8rem;
}

.purchase-reveal__eyebrow,
.purchase-reveal__name,
.purchase-reveal__meta,
.purchase-reveal__guide { margin: 0; }
.purchase-reveal__eyebrow { color: var(--reveal-color); font-size: .7rem; font-weight: 850; letter-spacing: .06em; }
.purchase-reveal__name { margin-top: 5px; font-size: 1.35rem; }
.purchase-reveal__meta { margin-top: 5px; font-size: .76rem; opacity: .66; }
.purchase-reveal__coins { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.purchase-reveal__coins span { padding: 6px 10px; border-radius: 999px; background: color-mix(in srgb, var(--reveal-color) 11%, transparent); font-size: .72rem; font-weight: 750; }
.purchase-reveal__guide { margin-top: 13px; font-size: .72rem; line-height: 1.5; opacity: .7; }

@keyframes purchase-reveal-enter {
  from { opacity: 0; transform: translateY(14px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes purchase-reveal-shine {
  from { left: -25%; opacity: 0; }
  35% { opacity: 1; }
  to { left: 120%; opacity: 0; }
}
@keyframes purchase-item-arrive {
  from { opacity: 0; transform: translateY(12px) scale(.72) rotate(-5deg); }
  to { opacity: 1; transform: translateY(0) scale(1) rotate(0); }
}

@media (max-width: 650px) {
  .purchase-reveal { grid-template-columns: 1fr; text-align: center; }
  .purchase-reveal__coins { justify-content: center; }
}
@media (prefers-reduced-motion: reduce) {
  .purchase-reveal,
  .purchase-reveal__shine,
  .purchase-reveal__visual img { animation: none; }
}
"""


_PURCHASE_REVEAL_JS = """
export default function (component) {
  const { data, parentElement } = component
  const root = parentElement.querySelector(".purchase-reveal")
  const visual = parentElement.querySelector(".purchase-reveal__visual")
  if (!root || !visual || !data) return

  const text = (selector, value) => {
    const target = parentElement.querySelector(selector)
    if (target) target.textContent = String(value)
  }

  root.dataset.rarity = String(data.rarity || "common")
  visual.replaceChildren()
  if (data.thumbnail) {
    const image = document.createElement("img")
    image.src = data.thumbnail
    image.alt = data.item_name
    image.draggable = false
    visual.append(image)
  } else {
    const placeholder = document.createElement("span")
    placeholder.className = "purchase-reveal__placeholder"
    placeholder.textContent = "◇"
    visual.append(placeholder)
  }

  text(".purchase-reveal__name", data.item_name)
  text(".purchase-reveal__meta", `${data.rarity_label} · ${data.category_label}`)
  text(".purchase-reveal__spent", `${data.coins_spent} 코인 사용`)
  text(".purchase-reveal__balance", `남은 코인 ${data.balance}개`)
}
"""


_PURCHASE_REVEAL = st.components.v2.component(
    "shop_purchase_reveal",
    html=_PURCHASE_REVEAL_HTML,
    css=_PURCHASE_REVEAL_CSS,
    js=_PURCHASE_REVEAL_JS,
)


def render_shop_purchase_reveal(
    feedback: Mapping[str, Any],
    *,
    key: str,
) -> bool:
    """새 구매 결과를 한 번 보여주고 테스트 환경 지원 여부를 반환합니다."""

    if feedback.get("newly_purchased") is not True:
        return False
    try:
        _PURCHASE_REVEAL(
            key=key,
            data=dict(feedback),
            height="content",
        )
        return True
    except ValueError as error:
        if "Component 'shop_purchase_reveal' is not registered" in str(error):
            return False
        raise
