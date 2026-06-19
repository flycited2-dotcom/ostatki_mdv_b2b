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
import shutil
import time
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

# THAICON — фото локальные (папка разложена по сериям). Путь — env JAC_THAICON_DIR
# (на ПК указывает на «Фото Thaicon»). Берём фото внутреннего блока на серию, копируем
# в data/photos/, в jac_photos кладём имя файла (бот отдаёт его фотоген-агенту байтами).
THAICON_DIR = os.environ.get("JAC_THAICON_DIR", "")


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


def thaicon_photos(src_dir, out_photos_dir) -> dict:
    """Скан локальной папки THAICON (категория/серия/Внутренний блок/*.png).
    Копирует представительное фото на серию в out_photos_dir, возвращает
    {НОРМ_СЕРИЯ: имя_файла}. Папки нет → {}."""
    src = Path(src_dir)
    if not src.is_dir():
        return {}
    out = Path(out_photos_dir)
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, str] = {}
    for cat in src.iterdir():
        if not cat.is_dir():
            continue
        for series_dir in cat.iterdir():
            if not series_dir.is_dir():
                continue
            inner = series_dir / "Внутренний блок"
            pics = list(inner.glob("*.png")) if inner.is_dir() else []
            if not pics:                              # запас: любой png в дереве серии
                pics = list(series_dir.rglob("*.png"))
            pics = [p for p in pics if p.is_file()]
            if not pics:
                continue
            chosen = min(pics, key=lambda p: p.stat().st_size)   # самый лёгкий файл серии
            if chosen.stat().st_size > 20 * 1024 * 1024:         # >20 МБ — тяжело, пропускаем
                logger.warning("THAICON %s: минимальное фото >20МБ — пропускаю", series_dir.name)
                continue
            key = normalize_series(series_dir.name)
            base = "THAICON__" + re.sub(r"[^A-Z0-9]+", "_", key).strip("_") + ".png"
            shutil.copyfile(chosen, out / base)
            res[key] = base
    return res


def _fetch_json(url, settings, retries=3):
    headers = {"User-Agent": settings.user_agent}
    last = None
    for i in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=settings.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:                       # noqa: BLE001 — транзиентные сбои ретраим
            last = e
            logger.warning("экспорт %s попытка %d/%d: %s", url, i, retries, e)
            time.sleep(2)
    raise last


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

    # Прежний результат — чтобы НЕ затереть бренд, если экспорт временно недоступен.
    out_path = out_dir / "jac_photos_latest.json"
    prev: dict[str, dict] = {}
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}

    result: dict[str, dict] = {}
    for brand, urls in EXPORT_URLS.items():
        items = []
        for url in urls:
            try:
                items += _fetch_json(url, settings)
            except Exception as e:                       # noqa: BLE001
                logger.warning("экспорт %s недоступен (%s)", url, e)
        photo_map = export_photo_map(items)
        bp = build_brand_photos(by_brand.get(brand, set()), photo_map, OVERRIDES.get(brand))
        have = len(by_brand.get(brand, set()))
        print(f"[photos] {brand}: серий в наличии {have}, фото найдено {len(bp)}")
        if bp:
            result[brand] = bp
        elif prev.get(brand):                            # экспорт пуст → сохраняем прежнее
            result[brand] = prev[brand]
            print(f"[photos] {brand}: экспорт недоступен — сохранил прежние {len(prev[brand])} фото")

    # THAICON — локальные файлы по сериям (если задан JAC_THAICON_DIR). Читаем в рантайме:
    # .env подгружается в load_settings() уже ПОСЛЕ импорта модуля.
    thaicon_dir = os.environ.get("JAC_THAICON_DIR", "") or THAICON_DIR
    if thaicon_dir:
        tmap = thaicon_photos(thaicon_dir, out_dir / "photos")
        bp = build_brand_photos(by_brand.get("THAICON", set()), tmap, OVERRIDES.get("THAICON"))
        have = len(by_brand.get("THAICON", set()))
        print(f"[photos] THAICON: серий в наличии {have}, фото найдено {len(bp)} (локальные)")
        if bp:
            result["THAICON"] = bp
        elif prev.get("THAICON"):
            result["THAICON"] = prev["THAICON"]
    elif prev.get("THAICON"):
        result["THAICON"] = prev["THAICON"]
        print("[photos] THAICON: JAC_THAICON_DIR не задан — сохранил прежние")
    else:
        print("[photos] THAICON: JAC_THAICON_DIR не задан — пропускаю")

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in result.values())
    print(f"[photos] ✓ {out_path} — брендов {len(result)}, фото-серий {total}")
    return 0
