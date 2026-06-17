"""CLI: python -m jac_scraper <команда>

Команды:
  check       — проверить авторизацию (логин/пароль или cookie) и доступ к бланку
  discover    — сохранить реальный HTML и показать структуру (калибровка парсера)
  scrape      — собрать остатки+цены и выгрузить в data/ (csv/json/xlsx)
  utp-collect — обойти сайты вендоров, собрать УТП-кандидаты, записать xlsx для вычитки
  utp-build   — собрать финальный jac_utp_latest.json из отмеченного xlsx
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_settings
from .session import authenticate, AuthError
from .catalog import fetch_all
from .discover import run_discover
from .export import export_all
from .specs import fetch_specs, SPECS_FILE
from .utp import (
    write_candidates, build_latest_from_xlsx, coverage_gaps,
    CANDIDATES_XLSX, CANDIDATES_JSON, LATEST_JSON,
)
from .utp_sites import BRAND_CONFIGS, collect_brand


def cmd_check(settings) -> int:
    problem = settings.credentials_problem()
    if problem:
        print(f"[check] ✗ {problem}")
        return 2
    try:
        authenticate(settings)
    except AuthError as e:
        print(f"[check] ✗ {e}")
        return 2
    print("[check] ✓ авторизация успешна, бланк доступен.")
    return 0


def cmd_discover(settings) -> int:
    try:
        session = authenticate(settings)
    except AuthError as e:
        print(f"[discover] ✗ {e}")
        return 2
    run_discover(session, settings)
    return 0


def cmd_scrape(settings) -> int:
    try:
        session = authenticate(settings)
    except AuthError as e:
        print(f"[scrape] ✗ {e}")
        return 2

    products = fetch_all(session, settings)
    if not products:
        print(
            "[scrape] ✗ позиций не найдено. Похоже, верстка отличается от ожидаемой — "
            "запусти `python -m jac_scraper discover` для калибровки."
        )
        return 3

    written = export_all(products, settings.output_dir, settings.output_formats)
    print(f"\n[scrape] ✓ собрано позиций: {len(products)}")
    for path in written:
        print(f"  → {path}")
    return 0


def cmd_specs(settings, refresh=False) -> int:
    """Тянет характеристики карточек для товаров из последнего jac_stock_latest.json."""
    stock_file = settings.output_dir / "jac_stock_latest.json"
    try:
        products = json.loads(stock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"[specs] ✗ нет {stock_file}. Сначала запусти `scrape`.")
        return 3
    try:
        session = authenticate(settings)
    except AuthError as e:
        print(f"[specs] ✗ {e}")
        return 2
    fetch_specs(session, settings, products, refresh=refresh)
    print(f"[specs] ✓ готово -> {settings.output_dir / SPECS_FILE}")
    return 0


_TYPE_WORDS = ("сплит-система", "канальн", "кассетн", "мульти", "колонн", "напольн")


def cmd_utp_collect(settings) -> int:
    """Обходит сайты вендоров, собирает УТП-кандидаты, пишет xlsx для вычитки."""
    from .session import new_session
    session = new_session(settings)

    cands = []
    for brand, cfg in BRAND_CONFIGS.items():
        cands.extend(collect_brand(session, settings, brand, cfg))
    if not cands:
        print("[utp-collect] ✗ кандидатов не собрано — проверь селекторы в BRAND_CONFIGS.")
        return 3

    xlsx_path = settings.output_dir / CANDIDATES_XLSX
    json_path = settings.output_dir / CANDIDATES_JSON
    write_candidates(cands, xlsx_path, json_path)
    print(f"[utp-collect] ✓ кандидатов {len(cands)} → {xlsx_path}")

    stock_file = settings.output_dir / "jac_stock_latest.json"
    if stock_file.exists():
        products = json.loads(stock_file.read_text(encoding="utf-8"))
        jac_series: dict = {}
        for p in products:
            jac_series.setdefault(p.get("brand", ""), [])
            s = p.get("series", "")
            if s and s not in jac_series[p.get("brand", "")]:
                jac_series[p.get("brand", "")].append(s)
        gaps = coverage_gaps(jac_series, cands, _TYPE_WORDS)
        if gaps:
            print("[utp-collect] серии JAC без УТП (допиши руками в xlsx при необходимости):")
            for brand, names in gaps.items():
                print(f"  {brand}: {', '.join(names)}")
    return 0


def cmd_utp_build(settings) -> int:
    """Собирает финальный jac_utp_latest.json из отмеченного xlsx."""
    xlsx_path = settings.output_dir / CANDIDATES_XLSX
    if not xlsx_path.exists():
        print(f"[utp-build] ✗ нет {xlsx_path}. Сначала запусти `utp-collect`.")
        return 3
    out_path = settings.output_dir / LATEST_JSON
    result = build_latest_from_xlsx(xlsx_path, out_path)
    total = sum(len(v) for series in result.values() for v in series.values())
    print(f"[utp-build] ✓ серий {sum(len(s) for s in result.values())}, "
          f"УТП {total} → {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jac_scraper", description="Сбор остатков и цен с b2b-jac.com")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="проверить авторизацию")
    sub.add_parser("discover", help="сохранить HTML и показать структуру для калибровки")
    sub.add_parser("scrape", help="собрать данные и выгрузить в файлы")
    sp = sub.add_parser("specs", help="собрать характеристики (ТТХ) карточек товаров")
    sp.add_argument("--refresh", action="store_true", help="перетянуть все ТТХ заново (игнор кэша)")
    sub.add_parser("utp-collect", help="собрать УТП-кандидаты с сайтов вендоров в xlsx")
    sub.add_parser("utp-build", help="собрать финальный jac_utp_latest.json из отмеченного xlsx")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.command == "specs":
        return cmd_specs(settings, refresh=getattr(args, "refresh", False))
    return {
        "check": cmd_check,
        "discover": cmd_discover,
        "scrape": cmd_scrape,
        "utp-collect": cmd_utp_collect,
        "utp-build": cmd_utp_build,
    }[args.command](settings)


if __name__ == "__main__":
    sys.exit(main())
