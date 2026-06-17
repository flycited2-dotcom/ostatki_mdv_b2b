"""Обход категорий бланка заказа b2b-jac.com под авторизованной сессией.

Особенности портала (выяснено разведкой):
  - корень /orders/blank_zakaza/ показывает только дерево категорий (0 товаров);
  - товары — внутри категорий; верхнеуровневая категория агрегирует весь свой
    подраздел с пагинацией;
  - параметр SIZEN_1 игнорируется (всегда 10 на страницу);
  - перелёт за последнюю страницу (PAGEN_1 слишком большой) возвращает НЕ пусто,
    а «склеенную» страницу -> нельзя останавливаться по «0 товаров».
    Поэтому берём максимальный номер страницы из пагинации и идём 1..max.
"""
from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import Settings
from .models import Product
from .parse import parse_products, dedupe
from .session import authenticate, looks_authenticated, AuthError

_TOP_CAT_RE = re.compile(r"^/orders/blank_zakaza/(\d+)/$")
_PAGEN_RE = re.compile(r"PAGEN_1=(\d+)")


def _get(session: requests.Session, url: str, settings: Settings) -> Optional[requests.Response]:
    last = None
    for attempt in range(settings.retries + 1):
        try:
            return session.get(url, timeout=settings.timeout, allow_redirects=True)
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  ! сеть: не удалось получить {url}: {last}")
    return None


def discover_top_categories(session: requests.Session, settings: Settings) -> List[Tuple[str, str]]:
    """Возвращает список (path, название) верхнеуровневых категорий из корня бланка."""
    url = f"{settings.base_url}/orders/blank_zakaza/"
    resp = _get(session, url, settings)
    if resp is None:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    cats: List[Tuple[str, str]] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        if _TOP_CAT_RE.match(a["href"]) and a["href"] not in seen:
            seen.add(a["href"])
            cats.append((a["href"], " ".join(a.get_text(" ").split())))
    return cats


def _max_page(soup: BeautifulSoup) -> int:
    nums = [int(m) for m in _PAGEN_RE.findall(str(soup))]
    return max(nums) if nums else 1


# Размер страницы пагинации. ВАЖНО: PAGEN_1 и SIZEN_1 указываем явно в КАЖДОМ
# запросе — иначе Битрикс берёт номер страницы/размер из сессии, и при длинном
# последовательном обходе страницы за ~10-й начинают возвращаться пустыми.
_PAGE_SIZE = 10


def _page_url(settings: Settings, path: str, page: int) -> str:
    return f"{settings.base_url}{path}?PAGEN_1={page}&SIZEN_1={_PAGE_SIZE}"


def fetch_category(session: requests.Session, settings: Settings, path: str,
                   name: str, max_pages_cap: int = 500) -> List[Product]:
    """Тянет все страницы одной категории (1..max) и парсит товары."""
    resp = _get(session, _page_url(settings, path, 1), settings)
    if resp is None:
        return []
    session = _ensure_auth(session, settings, resp)
    if session is None:
        return []

    last_page = min(_max_page(BeautifulSoup(resp.text, "lxml")), max_pages_cap)
    collected = parse_products(resp.text, category=name)
    print(f"  [{name}] стр.1/{last_page}: {len(collected)}")

    for page in range(2, last_page + 1):
        url = _page_url(settings, path, page)
        time.sleep(0.4)  # вежливая пауза
        r = _get(session, url, settings)
        if r is None:
            continue
        session2 = _ensure_auth(session, settings, r)
        if session2 is None:
            break
        session = session2
        products = parse_products(r.text, category=name)
        collected.extend(products)
        print(f"  [{name}] стр.{page}/{last_page}: {len(products)}")
    return collected


_reauth_done = {"v": False}


def _ensure_auth(session, settings, resp):
    """Если сессия истекла (портал вернул форму логина) — одна переавторизация."""
    if looks_authenticated(resp.text):
        return session
    if _reauth_done["v"]:
        print("  ! доступ потерян после повторной авторизации")
        return None
    print("  сессия истекла — повторная авторизация…")
    try:
        new = authenticate(settings)
    except AuthError as e:
        print(f"  ! не удалось переавторизоваться: {e}")
        return None
    _reauth_done["v"] = True
    return new


def fetch_all(session: requests.Session, settings: Settings) -> List[Product]:
    """Собирает товары по всем верхнеуровневым категориям бланка заказа."""
    _reauth_done["v"] = False
    cats = discover_top_categories(session, settings)
    if not cats:
        # запасной вариант — пути из конфига
        cats = [(p, p.strip("/").split("/")[-1]) for p in settings.blank_paths]
        print("Категории не найдены в корне — использую JAC_BLANK_PATHS.")
    else:
        print(f"Найдено верхнеуровневых категорий: {len(cats)}")

    all_products: List[Product] = []
    for path, name in cats:
        print(f"Категория: {name}  ({path})")
        all_products.extend(fetch_category(session, settings, path, name))

    result = dedupe(all_products)
    print(f"Итого уникальных позиций: {len(result)} (до дедупа {len(all_products)})")
    return result
