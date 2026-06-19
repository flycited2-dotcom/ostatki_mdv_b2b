"""Карта фото серий JAC: {бренд: {СЕРИЯ_остатков: URL_фото}} -> jac_photos_latest.json.

Источник для MDV/MHI — официальные экспорт-каталоги вендоров (JSON): у каждого товара
есть серия (`SECTIONS.SECTION_3`) и АБСОЛЮТНЫЙ URL фото (`PREVIEW_PICTURE`). Берём по
одному представительному фото на серию и привязываем к сериям из наших остатков
(`jac_stock_latest.json`).

Сложность: имена серий в остатках (из пути категории портала) и в экспорте вендора
не совпадают дословно («AURORA ON/OFF R32» ↔ «Aurora R32 On/Off»). Поэтому матчим:
точная нормализация → ручной override → токенный матч (Жаккар) с порогом — рискованные
неоднозначные совпадения НЕ берём (лучше без фото, чем чужое фото).

THAICON (локальные файлы) и EUROKLIMAT (каталог сайта) — отдельным шагом (TODO).
ЧИСТЫЕ функции тестируются без сети (tests/test_photos.py).
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path

import requests

logger = logging.getLogger("jac_scraper.photos")

# Экспорт-каталоги вендоров (JSON: NAME/SECTIONS.SECTION_3/PREVIEW_PICTURE-URL).
EXPORT_URLS = {
    "MDV": [
        "https://mdv-aircond.ru/upload/export/bytovye-split-sistemy_export.json",
        "https://mdv-aircond.ru/upload/export/polupromyshlennye-split-sistemy_export.json",
    ],
    "Mitsubishi Heavy": [
        "https://mhi-aircond.ru/upload/export_mhi/bytovye-split-sistemy_export.json",
    ],
}

# Ручные соответствия «серия остатков -> серия экспорта» там, где токенный матч не берёт
# (напр. MHI: в остатках «STANDARD», в экспорте «SRK-ZSP-W STANDARD»). Ключи/значения
# сравниваются по normalize_series. Заполнять при необходимости.
OVERRIDES: dict[str, dict[str, str]] = {
    "Mitsubishi Heavy": {},
}

MATCH_THRESHOLD = 0.6   # Жаккар по токенам; ниже — считаем матч ненадёжным


def normalize_series(s) -> str:
    return " ".join((s or "").upper().split())


def _tokens(s) -> set:
    return {t for t in re.split(r"[^A-Z0-9]+", normalize_series(s)) if t}


def export_photo_map(items) -> dict:
    """Список товаров экспорта -> {НОРМ_СЕРИЯ: URL_фото}; первый непустой на серию."""
    out: dict[str, str] = {}
    for p in items:
        sec = normalize_series((p.get("SECTIONS") or {}).get("SECTION_3"))
        pic = (p.get("PREVIEW_PICTURE") or "").strip()
        if sec and pic and sec not in out:
            out[sec] = pic
    return out


def match_photo(stock_series, photo_map, overrides=None, threshold=MATCH_THRESHOLD):
    """URL фото для серии остатков: точное → override → токенный матч ≥ порога; иначе None."""
    key = normalize_series(stock_series)
    if key in photo_map:
        return photo_map[key]
    if overrides:
        tgt = normalize_series(overrides.get(key) or overrides.get(stock_series or ""))
        if tgt and tgt in photo_map:
            return photo_map[tgt]
    tt = _tokens(stock_series)
    if not tt:
        return None
    best, best_score = None, 0.0
    for cand, url in photo_map.items():
        ct = _tokens(cand)
        score = len(tt & ct) / max(len(tt | ct), 1)
        if score > best_score:
            best, best_score = url, score
    return best if best_score >= threshold else None


def build_brand_photos(stock_series_list, photo_map, overrides=None) -> dict:
    """{НОРМ_СЕРИЯ_остатков: URL} — только для серий, которым нашлось фото."""
    out: dict[str, str] = {}
    for s in stock_series_list:
        url = match_photo(s, photo_map, overrides)
        if url:
            out[normalize_series(s)] = url
    return out


def _fetch_json(url, settings):
    headers = {"User-Agent": settings.user_agent}
    r = requests.get(url, headers=headers, timeout=settings.timeout)
    r.raise_for_status()
    return r.json()


def cmd_photos(settings) -> int:
    os.environ.setdefault("NO_PROXY", "*")   # мимо системного SOCKS-прокси на ПК
    out_dir = Path(settings.output_dir)
    stock_path = out_dir / "jac_stock_latest.json"
    if not stock_path.exists():
        logger.error("нет %s — сначала запусти scrape", stock_path)
        return 1

    stock = json.loads(stock_path.read_text(encoding="utf-8"))
    by_brand: dict[str, set] = defaultdict(set)
    for p in stock:
        b = (p.get("brand") or "").strip()
        s = (p.get("series") or "").strip()
        if b and s:
            by_brand[b].add(s)

    result: dict[str, dict] = {}
    for brand, urls in EXPORT_URLS.items():
        items = []
        for url in urls:
            try:
                items += _fetch_json(url, settings)
            except Exception as e:                       # noqa: BLE001
                logger.warning("экспорт %s недоступен (%s) — пропускаю", url, e)
        photo_map = export_photo_map(items)
        bp = build_brand_photos(by_brand.get(brand, set()), photo_map, OVERRIDES.get(brand))
        have = len(by_brand.get(brand, set()))
        print(f"[photos] {brand}: серий в наличии {have}, фото найдено {len(bp)}")
        if bp:
            result[brand] = bp

    out_path = out_dir / "jac_photos_latest.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in result.values())
    print(f"[photos] ✓ {out_path} — брендов {len(result)}, фото-серий {total}")
    return 0
