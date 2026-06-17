"""Характеристики (ТТХ) товаров JAC с карточек товара (блок bzd-props).

ТТХ практически не меняются, поэтому работаем КЭШ-ориентированно: результат
пишем в data/jac_specs_latest.json ({артикул: {brand, series, characteristics}}).
Первый прогон тянет все карточки (~500, ~3 мин), последующие — только новые
модели (если не задан refresh). Источник списка товаров с путями — последний
jac_stock_latest.json (его готовит команда scrape).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup

from .config import Settings

SPECS_FILE = "jac_specs_latest.json"


def parse_characteristics(html: str) -> dict:
    """HTML карточки -> {название_характеристики: значение} (включая скрытые строки)."""
    soup = BeautifulSoup(html or "", "lxml")
    out: dict = {}
    for tr in soup.select("tr.bzd-props__table-row"):
        cols = tr.select("td.bzd-props__table-col")
        if len(cols) >= 2:
            k = " ".join(cols[0].get_text(" ").split())
            v = " ".join(cols[1].get_text(" ").split())
            if k and k not in out:
                out[k] = v
    return out


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_specs(session: requests.Session, settings: Settings,
                products: List[dict], refresh: bool = False) -> tuple[dict, int]:
    """Тянет ТТХ карточек для товаров с путём. Кэш-ориентированно.
    products — список dict (как в jac_stock_latest.json: article, path, brand, series).
    """
    out_path = settings.output_dir / SPECS_FILE
    cache = {} if refresh else _load_json(out_path)

    targets = [p for p in products if p.get("path") and p.get("article")]
    todo = [p for p in targets if refresh or p["article"] not in cache]
    print(f"Карточек к загрузке: {len(todo)} (в кэше уже {len(cache)})")

    new = 0
    for i, p in enumerate(todo, 1):
        url = settings.base_url + p["path"]
        try:
            r = session.get(url, timeout=settings.timeout)
        except requests.RequestException as e:
            print(f"  ! {p['article']}: сеть {e}")
            continue
        ch = parse_characteristics(r.text)
        if ch:
            cache[p["article"]] = {
                "brand": p.get("brand", ""),
                "series": p.get("series", ""),
                "characteristics": ch,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            new += 1
        if new and new % 25 == 0:
            _save(out_path, cache)        # промежуточное сохранение от сбоя
            print(f"  ...{new}/{len(todo)} (сохранено)")
        time.sleep(0.35)                  # вежливая пауза

    _save(out_path, cache)
    print(f"ТТХ: добавлено {new}, всего в кэше {len(cache)} -> {out_path}")
    return cache, new
