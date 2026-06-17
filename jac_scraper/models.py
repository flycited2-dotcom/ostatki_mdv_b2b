"""Нормализованная модель товара и помощники нормализации чисел."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# Текстовые маркеры наличия, которые встречаются вместо числа на складе.
# Возвращаем их как stock_raw, а stock_qty оставляем None.
_STOCK_WORD_RE = re.compile(
    r"(в наличии|есть|много|мало|ограничен|под заказ|ожидается|нет в наличии|нет|отсутству)",
    re.IGNORECASE,
)


def normalize_number(value: Optional[str]) -> Optional[float]:
    """Превращает строку с числом из верстки Битрикса в float.

    Понимает форматы: "1 234,50", "1 234.50", "12 345 руб.", "1.234,00",
    "—", "". Возвращает None, если числа нет.
    """
    if value is None:
        return None
    s = str(value)
    # убрать валюту/единицы/неразрывные пробелы/обычные пробелы как разделители тысяч
    s = s.replace(" ", " ").replace(" ", " ")
    # вытащить кусок, похожий на число (цифры, пробелы, точки, запятые)
    m = re.search(r"[-+]?[\d][\d \.\,]*", s)
    if not m:
        return None
    num = m.group(0).strip().replace(" ", "")
    if not re.search(r"\d", num):
        return None

    # Определяем десятичный разделитель.
    if "," in num and "." in num:
        # тот, что правее — десятичный
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        # запятая — десятичный разделитель (рус. формат)
        num = num.replace(",", ".")
    elif "." in num:
        # Только точки. В рус. вёрстке точка часто — разделитель ТЫСЯЧ
        # ("1.250 руб." = 1250), а не десятичный. Разбираем:
        parts = num.split(".")
        if len(parts) > 2:
            # несколько точек: все — тысячные ("1.234.567" -> 1234567)
            num = "".join(parts)
        elif len(parts[1]) == 3:
            # один разделитель, ровно 3 цифры после -> тысячи ("1.250" -> 1250)
            # (десятичные цены пишут с 2 знаками: "1250.50" остаётся как есть)
            num = parts[0] + parts[1]
        # иначе (1-2 знака после точки) — это десятичная дробь, оставляем

    try:
        return float(num)
    except ValueError:
        return None


def parse_stock(value: Optional[str]) -> tuple[Optional[float], str]:
    """Возвращает (числовой_остаток | None, исходный_текст).

    Если в ячейке слово ("много"/"под заказ") — число None, текст сохраняем.
    """
    raw = "" if value is None else str(value).strip()
    qty = normalize_number(raw)
    return qty, raw


@dataclass
class Product:
    article: str = ""              # артикул / код / модель
    name: str = ""                 # наименование
    brand: str = ""                # бренд / производитель (если есть)
    stock_qty: Optional[float] = None   # числовой остаток (колонка "Наличие")
    stock_raw: str = ""            # исходный текст наличия ("0 шт", "69 шт", "много")
    price: Optional[float] = None  # ЦЕНА (на портале JAC — "Ваша цена", цена дилера)
    currency: str = "RUB"
    unit: str = ""                 # ед. изм. (шт, компл.)
    warehouse: str = ""            # склад (если есть единый)
    category: str = ""             # категория/раздел бланка
    # доп. колонки как есть: РРЦ, Холод кВт, остатки по складам (Крым/Москва) и т.п.
    attributes: dict = field(default_factory=dict)
    source: str = "jac_b2b"
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_valid(self) -> bool:
        """Строка считается товаром, если есть осмысленный артикул или название
        и хотя бы цена или остаток."""
        has_id = bool(self.article.strip()) or len(self.name.strip()) >= 3
        has_data = (self.price is not None) or (self.stock_qty is not None) or bool(self.stock_raw)
        return has_id and has_data

    def to_dict(self) -> dict:
        return asdict(self)


# Базовые колонки экспорта (доп. колонки из attributes добавляются динамически).
EXPORT_COLUMNS = [
    "article", "name", "brand", "category",
    "stock_qty", "stock_raw",
    "price", "currency", "unit", "warehouse",
    "source", "scraped_at",
]

# Русские заголовки для CSV/XLSX.
EXPORT_HEADERS_RU = {
    "article": "Артикул/Модель",
    "name": "Наименование",
    "brand": "Бренд",
    "category": "Категория",
    "stock_qty": "Остаток (число)",
    "stock_raw": "Наличие (текст)",
    "price": "Ваша цена",
    "currency": "Валюта",
    "unit": "Ед.",
    "warehouse": "Склад",
    "source": "Источник",
    "scraped_at": "Собрано (UTC)",
}
