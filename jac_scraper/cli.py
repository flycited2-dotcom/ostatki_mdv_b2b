"""CLI: python -m jac_scraper <команда>

Команды:
  check     — проверить авторизацию (логин/пароль или cookie) и доступ к бланку
  discover  — сохранить реальный HTML и показать структуру (калибровка парсера)
  scrape    — собрать остатки+цены и выгрузить в data/ (csv/json/xlsx)
"""
from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .session import authenticate, AuthError
from .catalog import fetch_all
from .discover import run_discover
from .export import export_all


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jac_scraper", description="Сбор остатков и цен с b2b-jac.com")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="проверить авторизацию")
    sub.add_parser("discover", help="сохранить HTML и показать структуру для калибровки")
    sub.add_parser("scrape", help="собрать данные и выгрузить в файлы")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    return {
        "check": cmd_check,
        "discover": cmd_discover,
        "scrape": cmd_scrape,
    }[args.command](settings)


if __name__ == "__main__":
    sys.exit(main())
