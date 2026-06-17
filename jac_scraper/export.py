"""Экспорт списка Product в CSV / JSON / XLSX."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List

from .models import Product, EXPORT_COLUMNS, EXPORT_HEADERS_RU


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d")


def _attr_keys(products: List[Product]) -> List[str]:
    """Объединение ключей attributes по всем товарам, в порядке первого появления."""
    keys: List[str] = []
    for p in products:
        for k in p.attributes:
            if k not in keys:
                keys.append(k)
    return keys


def write_csv(products: List[Product], path: Path) -> Path:
    attr_keys = _attr_keys(products)
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM -> Excel дружит
        writer = csv.writer(f, delimiter=";")
        writer.writerow([EXPORT_HEADERS_RU[c] for c in EXPORT_COLUMNS] + attr_keys)
        for p in products:
            d = p.to_dict()
            row = [_fmt(d[c]) for c in EXPORT_COLUMNS]
            row += [_fmt(p.attributes.get(k, "")) for k in attr_keys]
            writer.writerow(row)
    return path


def write_json(products: List[Product], path: Path) -> Path:
    data = [p.to_dict() for p in products]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_xlsx(products: List[Product], path: Path) -> Path:
    from openpyxl import Workbook

    attr_keys = _attr_keys(products)
    wb = Workbook()
    ws = wb.active
    ws.title = "JAC остатки"
    header = [EXPORT_HEADERS_RU[c] for c in EXPORT_COLUMNS] + attr_keys
    ws.append(header)
    for p in products:
        d = p.to_dict()
        row = [d[c] for c in EXPORT_COLUMNS]
        row += [p.attributes.get(k, "") for k in attr_keys]
        ws.append(row)
    # автоширина (грубо)
    for col_idx, title in enumerate(header, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = \
            max(12, min(45, len(str(title)) + 4))
    wb.save(path)
    return path


def _fmt(v) -> str:
    if v is None:
        return ""
    return str(v)


def export_all(products: List[Product], output_dir: Path, formats: List[str]) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    written: List[Path] = []
    writers = {"csv": write_csv, "json": write_json, "xlsx": write_xlsx}
    for fmt in formats:
        fmt = fmt.lower().strip()
        if fmt not in writers:
            print(f"  ! неизвестный формат экспорта: {fmt}")
            continue
        path = output_dir / f"jac_stock_{stamp}.{fmt}"
        writers[fmt](products, path)
        written.append(path)

    # Стабильный файл для агрегатора (Telegram-бот SplitHome читает его как 4-го
    # поставщика). Всегда перезаписываем последним прогоном.
    latest = output_dir / "jac_stock_latest.json"
    write_json(products, latest)
    written.append(latest)
    return written
