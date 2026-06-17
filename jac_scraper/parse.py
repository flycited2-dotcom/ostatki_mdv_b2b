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
# Важно: "номенклатур" только в name (иначе крадёт колонку наименования);
# "руб" убран из price (это единица, а не название колонки — крал бы "Сумма руб.").
_HEADER_KEYWORDS = {
    "article": ["артикул", "код", "sku", "кат. номер", "каталожн"],
    "name": ["наименование", "название", "товар", "номенклатур", "описание", "модель"],
    "brand": ["бренд", "производитель", "марка", "brand"],
    "price": ["цена", "стоимость", "прайс", "price"],
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


def _field_scores(header: str) -> Dict[str, int]:
    """Для одного заголовка: поле -> длина самого специфичного совпавшего слова.

    Совпадение требует границы слова СЛЕВА (?<![а-яёa-z0-9]), поэтому "код" не
    ловит "штрихкод", а "ед" не ловит "передний". Длина слова = специфичность:
    "наименование"(12) бьёт "товар"(5) при конфликте.
    """
    h = _clean(header).lower()
    scores: Dict[str, int] = {}
    for field, keywords in _HEADER_KEYWORDS.items():
        best = 0
        for kw in keywords:
            if re.search(r"(?<![а-яёa-z0-9])" + re.escape(kw), h):
                best = max(best, len(kw))
        if best:
            scores[field] = best
    return scores


def detect_column_map(header_cells: List[str]) -> Dict[str, int]:
    """Сопоставляет поля колонкам по заголовкам.

    Жадно по убыванию специфичности: каждое поле и каждая колонка
    используются один раз. Это разруливает коллизии (напр. "Номенклатура"
    уходит в name, а не в article).
    """
    candidates = []  # (score, col_idx, field)
    for idx, raw in enumerate(header_cells):
        for field, score in _field_scores(raw).items():
            candidates.append((score, idx, field))
    candidates.sort(key=lambda c: (-c[0], c[1]))

    mapping: Dict[str, int] = {}
    used_cols: set[int] = set()
    for _score, idx, field in candidates:
        if field in mapping or idx in used_cols:
            continue
        mapping[field] = idx
        used_cols.add(idx)
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
    # имя — самая длинная текстовая ячейка без явной цены (если такая есть)
    def _name_score(i: int) -> int:
        return len(cells[i]) if i != price_idx and not _PRICE_RE.search(cells[i]) else -1

    best_idx = max(range(len(cells)), key=_name_score)
    name_idx = best_idx if _name_score(best_idx) > 0 else None
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


# --- Специализированный парсер бланка заказа b2b-jac.com (классы product__property--*) ---

# Классы ячеек, которые НЕ являются данными колонок таблицы:
#   --image        — превью товара (под colspan=2 заголовка "Наименование")
#   --price-mobile — дубль цены только для мобильной верстки
#   --quantity     — поле ввода количества (последняя колонка "Количество")
_SKIP_CELL_CLASSES = ("--image", "--price-mobile", "--quantity")


def _has_blank_markup(table) -> bool:
    return table.select_one("td.product__property, td[class*=product__property]") is not None


def _cell_classes(cell) -> str:
    return " ".join(cell.get("class", []))


def parse_blank_table(table, category: str = "") -> List[Product]:
    """Парсит таблицу бланка заказа JAC по семантическим классам.

    Колонки выравниваются по заголовку (без служебных ячеек image/mobile/quantity).
    "Наличие" -> остаток, "Ваша цена" -> цена, прочее (РРЦ, Холод кВт, склады
    Крым/Москва) -> attributes.
    """
    rows = table.find_all("tr")
    if not rows:
        return []

    # Заголовки без колонки "Количество" (это поле ввода, а не данные).
    raw_headers = [_clean(c.get_text(" ")) for c in rows[0].find_all(["th", "td"])]
    headers = [h for h in raw_headers if "количеств" not in h.lower()]

    products: List[Product] = []
    for r in rows[1:]:
        data_cells = [
            td for td in r.find_all("td")
            if not any(sk in _cell_classes(td) for sk in _SKIP_CELL_CLASSES)
        ]
        if not data_cells:
            continue
        values = [_clean(td.get_text(" ")) for td in data_cells]
        if not any(values) or _is_summary_row(r, values):
            continue

        link = r.select_one("a.product__link[data-href], a[data-href]")
        path = link.get("data-href", "") if link else ""
        p = Product(category=category, path=path)
        price_set = False
        for i, val in enumerate(values):
            header = headers[i] if i < len(headers) else ""
            hl = header.lower()
            if not p.name and ("наимен" in hl or "номенклатур" in hl or "модель" in hl):
                p.name = val
                p.article = val            # на этой витрине модель = идентификатор
            elif "наличие" in hl:
                p.stock_qty, p.stock_raw = parse_stock(val)
            elif not price_set and "цена" in hl:   # "Ваша цена"
                p.price = normalize_number(val)
                price_set = True
            elif header:
                if val:
                    p.attributes[header] = val
        if p.is_valid():
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


def parse_products(html: str, category: str = "") -> List[Product]:
    """Главная точка входа: HTML страницы -> список Product (с дедупликацией).

    Если таблица — бланк заказа JAC (классы product__property--*), используется
    специализированный парсер; иначе общий табличный/карточный.
    """
    soup = BeautifulSoup(html or "", "lxml")
    products: List[Product] = []
    for table in soup.find_all("table"):
        if _has_blank_markup(table):
            products.extend(parse_blank_table(table, category=category))
        else:
            products.extend(parse_table(table))
    if not products:
        products.extend(parse_cards(soup))
    return dedupe(products)


def dedupe(products: List[Product]) -> List[Product]:
    """Убирает дубли. Когда артикул есть — ключ (артикул, имя). Когда артикула
    нет — добавляем бренд и цену, чтобы не схлопнуть разные товары с одинаковым
    именем (M4)."""
    seen = set()
    out = []
    for p in products:
        art = p.article.lower().strip()
        if art:
            key = (art, p.name.lower())
        else:
            key = ("", p.name.lower(), p.brand.lower(), p.price)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
