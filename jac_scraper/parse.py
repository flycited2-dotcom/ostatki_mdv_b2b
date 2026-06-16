"""Парсинг HTML бланка заказа / каталога в список Product.

Парсер построен на устойчивых эвристиках, т.к. точная верстка
аутентифицированной страницы заранее неизвестна (нет логина на момент
разработки). Колонки определяются по заголовкам; при их отсутствии —
по содержимому ячеек. Калибруется командой `discover` под реальный HTML.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .models import Product, normalize_number, parse_stock

# Ключевые слова заголовков колонок -> логическое поле.
_HEADER_KEYWORDS = {
    "article": ["артикул", "код", "sku", "номенклатур", "кат. номер", "каталожн"],
    "name": ["наименование", "название", "товар", "номенклатура", "описание", "модель"],
    "brand": ["бренд", "производитель", "марка", "brand"],
    "price": ["цена", "стоимость", "прайс", "price", "руб"],
    "stock": ["остаток", "наличие", "склад", "кол-во", "количество", "доступно", "qty"],
    "unit": ["ед", "единица", "unit"],
}

_PRICE_RE = re.compile(r"\d[\d   .,]*\s*(?:руб|р\.|₽|rub)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d")
# Итоговые/служебные строки, которые НЕ являются товаром.
_SUMMARY_RE = re.compile(r"^\s*(итого|всего|сумма|подытог|total)\b", re.IGNORECASE)


def _is_summary_row(row, cells: List[str]) -> bool:
    cls = " ".join(row.get("class", [])) if hasattr(row, "get") else ""
    if re.search(r"\b(total|summary|itog|footer)\b", cls, re.IGNORECASE):
        return True
    return any(_SUMMARY_RE.match(c) for c in cells)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def detect_column_map(header_cells: List[str]) -> Dict[str, int]:
    """По текстам заголовков возвращает map поле->индекс колонки."""
    mapping: Dict[str, int] = {}
    for idx, raw in enumerate(header_cells):
        h = _clean(raw).lower()
        if not h:
            continue
        for field, keywords in _HEADER_KEYWORDS.items():
            if field in mapping:
                continue
            if any(kw in h for kw in keywords):
                mapping[field] = idx
                break
    return mapping


def _cells(row) -> List[str]:
    return [_clean(td.get_text(" ")) for td in row.find_all(["td", "th"])]


def _row_to_product(cells: List[str], cmap: Dict[str, int]) -> Optional[Product]:
    def cell(field: str) -> str:
        i = cmap.get(field)
        return cells[i] if i is not None and i < len(cells) else ""

    name = cell("name")
    article = cell("article")
    price = normalize_number(cell("price"))
    stock_qty, stock_raw = parse_stock(cell("stock"))

    p = Product(
        article=article,
        name=name,
        brand=cell("brand"),
        stock_qty=stock_qty,
        stock_raw=stock_raw,
        price=price,
        unit=cell("unit"),
    )
    return p if p.is_valid() else None


def _heuristic_row(cells: List[str]) -> Optional[Product]:
    """Без заголовков: ищем в строке цену, остаток, артикул, имя."""
    if len(cells) < 2:
        return None
    price = None
    price_idx = None
    for i, c in enumerate(cells):
        if _PRICE_RE.search(c):
            price = normalize_number(c)
            price_idx = i
            break
    # имя — самая длинная текстовая ячейка без явной цены
    name_idx = max(
        range(len(cells)),
        key=lambda i: len(cells[i]) if i != price_idx and not _PRICE_RE.search(cells[i]) else -1,
    )
    name = cells[name_idx] if name_idx is not None else ""
    if len(name) < 3 and price is None:
        return None
    # артикул — короткая ячейка с цифрами/буквами-цифрами, не имя и не цена
    article = ""
    for i, c in enumerate(cells):
        if i in (name_idx, price_idx):
            continue
        if re.fullmatch(r"[A-Za-zА-Яа-я0-9\-/.]{3,20}", c) and _NUMBER_RE.search(c):
            article = c
            break
    p = Product(article=article, name=name, price=price, stock_raw="")
    return p if p.is_valid() else None


def parse_table(table) -> List[Product]:
    rows = table.find_all("tr")
    if not rows:
        return []

    # ищем строку заголовков (с <th> или с ключевыми словами)
    header_cells = None
    data_start = 0
    for i, r in enumerate(rows[:3]):
        texts = _cells(r)
        cmap_try = detect_column_map(texts)
        if r.find("th") or len(cmap_try) >= 2:
            header_cells = texts
            data_start = i + 1
            break

    products: List[Product] = []
    if header_cells:
        cmap = detect_column_map(header_cells)
        for r in rows[data_start:]:
            cells = _cells(r)
            if not any(cells) or _is_summary_row(r, cells):
                continue
            p = _row_to_product(cells, cmap) if cmap else _heuristic_row(cells)
            if p:
                products.append(p)
    else:
        for r in rows:
            cells = _cells(r)
            if _is_summary_row(r, cells):
                continue
            p = _heuristic_row(cells)
            if p:
                products.append(p)
    return products


def parse_cards(soup: BeautifulSoup) -> List[Product]:
    """Резерв для div-карточек каталога (не табличная верстка)."""
    products: List[Product] = []
    candidates = soup.select(
        "[class*=item], [class*=product], [class*=catalog-item], [data-product-id]"
    )
    for el in candidates:
        text = el.get_text(" ")
        if not _PRICE_RE.search(text):
            continue
        name_el = el.select_one("[class*=title], [class*=name], a")
        name = _clean(name_el.get_text(" ")) if name_el else ""
        price = normalize_number(_PRICE_RE.search(text).group(0))
        art_el = el.select_one("[class*=article], [class*=artikul], [class*=sku]")
        article = _clean(art_el.get_text(" ")) if art_el else ""
        p = Product(article=article, name=name, price=price)
        if p.is_valid():
            products.append(p)
    return products


def parse_products(html: str) -> List[Product]:
    """Главная точка входа: HTML страницы -> список Product (с дедупликацией)."""
    soup = BeautifulSoup(html or "", "lxml")
    products: List[Product] = []
    for table in soup.find_all("table"):
        products.extend(parse_table(table))
    if not products:
        products.extend(parse_cards(soup))
    return _dedupe(products)


def _dedupe(products: List[Product]) -> List[Product]:
    seen = set()
    out = []
    for p in products:
        key = (p.article.lower(), p.name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
