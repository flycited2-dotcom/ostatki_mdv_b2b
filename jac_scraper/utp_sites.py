"""Сбор УТП по сериям с сайтов производителей.

Один общий экстрактор + конфиг под каждый бренд (вместо 4 отдельных парсеров).
Селекторы калибруются на сохранённых фикстурах (tests/fixtures/utp_<brand>_series.html).
"""
from __future__ import annotations

import time
from typing import List
from urllib.parse import urljoin

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


def parse_series_links(html: str, cfg: dict) -> dict:
    """HTML каталога -> {имя_серии: абсолютный_url} по cfg["series_link_selector"].

    Опционально cfg["name_selector"] задаёт CSS-селектор для текста названия серии
    внутри найденного <a> (или его ближайшего предка). Это нужно когда текст ссылки
    — «Подробнее», а настоящее имя серии находится в соседнем/дочернем элементе.
    """
    if not cfg.get("series_link_selector"):
        return {}
    soup = BeautifulSoup(html or "", "lxml")
    out: dict = {}
    name_sel = cfg.get("name_selector", "")
    for a in soup.select(cfg["series_link_selector"]):
        href = a.get("href", "")
        if not href:
            continue
        if name_sel:
            # search in a itself, then parent, then grandparent
            name_node = (
                a.select_one(name_sel)
                or (a.parent.select_one(name_sel) if a.parent else None)
                or (a.parent.parent.select_one(name_sel) if a.parent and a.parent.parent else None)
            )
            name = _clean(name_node.get_text(" ") if name_node else a.get_text(" "))
        else:
            name = _clean(a.get_text(" "))
        if name and href:
            out[name] = urljoin(cfg["base_url"], href)
    return out


def collect_brand(session, settings, brand: str, cfg: dict):
    """Обходит каталог бренда -> страницы серий -> УТП. Возвращает list[UtpCandidate].

    except Exception намеренно широкий: одиночные сетевые сбои по серии/каталогу
    не должны валить весь прогон — пропускаем и идём дальше.
    """
    from .utp import UtpCandidate

    cands = []
    if not cfg.get("series_link_selector"):
        print(f"  {brand}: пропуск (нет series_link_selector — УТП вводится вручную)")
        return cands

    catalog_url = urljoin(cfg["base_url"], cfg.get("catalog_path", "/catalog/"))
    try:
        cat_html = session.get(catalog_url, timeout=settings.timeout).text
    except Exception as e:
        print(f"  ! {brand}: каталог недоступен ({e})")
        return cands
    series_links = parse_series_links(cat_html, cfg)
    print(f"  {brand}: серий найдено {len(series_links)}")
    for name, url in series_links.items():
        try:
            html = session.get(url, timeout=settings.timeout).text
        except Exception as e:
            print(f"  ! {brand}/{name}: {e}")
            continue
        for text in extract_utp(html, cfg):
            cands.append(UtpCandidate(brand=brand, series=name, text=text))
        time.sleep(0.35)
    return cands


BRAND_CONFIGS = {
    "MDV": {
        "base_url": "https://mdv-aircond.ru",
        # Each .section-benefits__text-block is one benefit card in the #benefits section.
        # item_selector "h3" extracts the short title (УТП phrase) from each card.
        "selectors": ["#benefits .section-benefits__text-block"],
        "item_selector": "h3",
        # Inverter subcategory page — lists all inverter series (9 серий).
        # ОГРАНИЧЕНИЕ: on/off и вентиляционные серии находятся на соседних страницах
        # и в одном проходе не собираются (архитектура одноуровневого обхода).
        # Охват: ~9 из ~20 серий бытового раздела.
        "catalog_path": "/catalog/bytovye-split-sistemy/invertornye-split-sistemy/",
        # .catalog-subsection-box — карточка подсекции; внутри один <a> со ссылкой и именем.
        "series_link_selector": ".catalog-subsection-box a",
    },
    "THAICON": {
        "base_url": "https://thaicon-climate.com",
        # Each .detal-func__items is one benefit tab (Надежность, Эффективность, etc.)
        # No <li> inside — items are .detal-func__name divs (one per feature).
        "selectors": [".detal-func__items"],
        "item_selector": ".detal-func__name",
        # Страница бытовых сплит-систем — в header-навигации показаны все серии
        # обоих подразделов (инверторные + on/off) с именами.
        # Охват: все 6 бытовых серий THAICON LIFE.
        "catalog_path": "/catalog/thaicon-life/bytovye-split-sistemy/",
        # Header-навигация содержит список серий: li > a с именем и href.
        # ОГРАНИЧЕНИЕ: глобальная навигация также включает полупром/VRF/multi — фильтрация
        # происходит через urljoin (у посторонних серий другой base_url путь, они всё равно
        # скачиваются — небольшой лишний трафик). При желании уточнить фильтр выше.
        "series_link_selector": ".header-catalog__content .header-catalog__content__item li a",
        # Series name is the text of the <a> itself (clean in this nav)
    },
    "Mitsubishi Heavy": {
        "base_url": "https://mhi-aircond.ru",
        # Each .section-benefits__full-box is one benefit card in the #benefits section.
        # item_selector "h3" extracts the short title (УТП phrase) from each card.
        "selectors": ["#benefits .section-benefits__full-box"],
        "item_selector": "h3",
        # Настенные сплит-системы — основной бытовой раздел (5 серий).
        # Охват: все настенные серии MHI (5 из 5).
        "catalog_path": "/catalog/bytovye-split-sistemy/nastennye-split-sistemy/",
        # a.sectionlist__item — прямая ссылка на серию; текст содержит имя + «Подробнее».
        # name_selector уточняет откуда брать чистое имя серии.
        "series_link_selector": "a.sectionlist__item",
        "name_selector": ".sectionlist__textbox-title",
    },
    "EUROKLIMAT": {
        "base_url": "https://euroklimat.com.ru",
        # No per-series УТП block on site — only generic category SEO text and
        # shop-level advantages (delivery/price/support). Selectors left empty.
        "selectors": [],
        "item_selector": "li",
        # Нет обхода — parse_series_links вернёт {} при пустом series_link_selector.
        "catalog_path": "/catalog/",
        "series_link_selector": "",
    },
}
