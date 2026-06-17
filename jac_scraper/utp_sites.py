"""Сбор УТП по сериям с сайтов производителей.

Один общий экстрактор + конфиг под каждый бренд (вместо 4 отдельных парсеров).
Селекторы калибруются на сохранённых фикстурах (tests/fixtures/utp_<brand>_series.html).
"""
from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

_ADV_WORDS = ("преимущест", "особенност", "почему", "достоинств")
_MIN_LEN, _MAX_LEN = 3, 400


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def extract_utp(html: str, cfg: dict) -> List[str]:
    """HTML страницы серии -> список текстов УТП. cfg["selectors"] — CSS-селекторы
    блоков преимуществ для конкретного бренда (определяются по фикстуре)."""
    soup = BeautifulSoup(html or "", "lxml")
    out: List[str] = []
    seen = set()

    nodes = []
    for sel in cfg.get("selectors", []):
        nodes.extend(soup.select(sel))
    if not nodes:
        for h in soup.find_all(["h2", "h3"]):
            if any(w in h.get_text().lower() for w in _ADV_WORDS):
                sib = h.find_next(["ul", "ol", "div"])
                if sib:
                    nodes.append(sib)

    for node in nodes:
        items = node.select("li") or node.select(cfg.get("item_selector", "li"))
        for it in items:
            t = _clean(it.get_text(" "))
            if _MIN_LEN <= len(t) <= _MAX_LEN and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return out


BRAND_CONFIGS = {
    "MDV": {
        "base_url": "https://mdv-aircond.ru",
        # Each .section-benefits__text-block is one benefit card in the #benefits section.
        # item_selector "h3" extracts the short title (УТП phrase) from each card.
        "selectors": ["#benefits .section-benefits__text-block"],
        "item_selector": "h3",
    },
    "THAICON": {
        "base_url": "https://thaicon-climate.com",
        # Each .detal-func__items is one benefit tab (Надежность, Эффективность, etc.)
        # No <li> inside — items are .detal-func__name divs (one per feature).
        "selectors": [".detal-func__items"],
        "item_selector": ".detal-func__name",
    },
    "Mitsubishi Heavy": {
        "base_url": "https://mhi-aircond.ru",
        # Each .section-benefits__full-box is one benefit card in the #benefits section.
        # item_selector "h3" extracts the short title (УТП phrase) from each card.
        "selectors": ["#benefits .section-benefits__full-box"],
        "item_selector": "h3",
    },
    "EUROKLIMAT": {
        "base_url": "https://euroklimat.com.ru",
        # No per-series УТП block on site — only generic category SEO text and
        # shop-level advantages (delivery/price/support). Selectors left empty.
        "selectors": [],
        "item_selector": "li",
    },
}
