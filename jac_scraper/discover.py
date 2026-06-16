"""Режим калибровки: сохраняет реальный HTML и показывает структуру страницы,
чтобы донастроить селекторы парсера под фактическую верстку портала.

Запускается ОДИН раз после того, как появится рабочая авторизация:
    python -m jac_scraper discover
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup

from .config import Settings, PROJECT_ROOT
from .parse import detect_column_map, _cells, parse_products


DUMP_DIR = PROJECT_ROOT / "dumps"


def _save(name: str, content: str) -> Path:
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"{name}_{ts}.html"
    path.write_text(content, encoding="utf-8")
    return path


def describe_page(html: str) -> str:
    """Текстовый отчёт о таблицах/колонках/экспортных ссылках на странице."""
    soup = BeautifulSoup(html or "", "lxml")
    lines: List[str] = []

    tables = soup.find_all("table")
    lines.append(f"Найдено таблиц: {len(tables)}")
    for ti, table in enumerate(tables):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = _cells(rows[0])
        cmap = detect_column_map(header)
        lines.append(f"\n— Таблица #{ti}: строк={len(rows)}, колонок≈{len(header)}")
        lines.append(f"  Заголовки: {header[:12]}")
        lines.append(f"  Распознанные колонки: {cmap if cmap else '— (не распознаны, нужна ручная калибровка)'}")
        if len(rows) > 1:
            lines.append(f"  Пример строки: {_cells(rows[1])[:12]}")

    # ссылки на экспорт (часто бланк заказа умеет выгружать в Excel)
    export_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(" ").lower()
        if any(k in href + text for k in ["export", "excel", "xls", "csv", "выгруз", "скача"]):
            export_links.append((a.get_text(" ").strip(), a["href"]))
    if export_links:
        lines.append("\nВозможные ссылки экспорта (надёжнее парсинга!):")
        for text, href in export_links[:20]:
            lines.append(f"  • {text!r} -> {href}")

    products = parse_products(html)
    lines.append(f"\nТекущий парсер извлёк бы: {len(products)} позиций.")
    if products:
        sample = products[0]
        lines.append(f"  Пример: {sample.to_dict()}")
    return "\n".join(lines)


def run_discover(session: requests.Session, settings: Settings) -> None:
    paths = list(settings.blank_paths)
    if settings.catalog_path:
        paths.append(settings.catalog_path)

    for path in paths:
        url = path if path.startswith("http") else f"{settings.base_url}{path}"
        try:
            resp = session.get(url, timeout=settings.timeout, allow_redirects=True)
        except requests.RequestException as e:
            print(f"[discover] {url}: сетевая ошибка {e}")
            continue
        name = path.strip("/").replace("/", "_") or "root"
        saved = _save(name, resp.text)
        print(f"\n=== {url} (HTTP {resp.status_code}) ===")
        print(f"Сырой HTML сохранён: {saved}")
        print(describe_page(resp.text))
    print(
        "\nЕсли колонки распознаны неверно — пришли мне файл из dumps/ или "
        "отчёт выше, и я за пару минут откалибрую селекторы в parse.py."
    )
