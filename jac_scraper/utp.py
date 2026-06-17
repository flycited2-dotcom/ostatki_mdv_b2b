"""УТП по сериям: каркас сбора кандидатов и сборки финального файла.

Поток (см. дизайн-док):
  utp-collect -> data/jac_utp_candidates.xlsx (+ .json бэкап)
  владелец ставит галочки в колонке «Брать»
  utp-build   -> data/jac_utp_latest.json {бренд: {СЕРИЯ_НОРМ: [УТП...]}}
"""
from __future__ import annotations

from dataclasses import dataclass


def normalize_series(name: str) -> str:
    """Верхний регистр + схлопывание пробелов. Ключ для связки JAC <-> сайт."""
    return " ".join((name or "").upper().split())


def match_series(jac_series: str, candidate_index: dict, aliases: dict | None = None) -> str | None:
    """Возвращает оригинальное имя серии сайта для серии JAC или None.

    candidate_index: {НОРМ_имя_серии_сайта: оригинальное_имя_сайта}
    aliases: {НОРМ_имя_серии_JAC: НОРМ_имя_серии_сайта} — для расхождений написания
    """
    aliases = aliases or {}
    key = normalize_series(jac_series)
    key = aliases.get(key, key)
    return candidate_index.get(key)
