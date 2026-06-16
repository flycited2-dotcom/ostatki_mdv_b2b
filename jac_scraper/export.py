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


def write_csv(products: List[Product], path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM -> Excel дружит
        writer = csv.writer(f, delimiter=";")
        writer.writerow([EXPORT_HEADERS_RU[c] for c in EXPORT_COLUMNS])
        for p in products:
            d = p.to_dict()
            writer.writerow([_fmt(d[c]) for c in EXPORT_COLUMNS])
    return path


def write_json(products: List[Product], path: Path) -> Path:
    data = [p.to_dict() for p in products]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_xlsx(products: List[Product], path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "JAC остатки"
    ws.append([EXPORT_HEADERS_RU[c] for c in EXPORT_COLUMNS])
    for p in products:
        d = p.to_dict()
        ws.append([d[c] for c in EXPORT_COLUMNS])
    # автоширина (грубо)
    for col_idx, col in enumerate(EXPORT_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = \
            max(12, min(40, len(EXPORT_HEADERS_RU[col]) + 4))
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
    return written
