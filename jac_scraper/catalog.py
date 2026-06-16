"""Загрузка страниц бланка заказа / каталога под авторизованной сессией."""
from __future__ import annotations

import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .config import Settings
from .models import Product
from .parse import parse_products


def _get(session: requests.Session, url: str, settings: Settings) -> Optional[requests.Response]:
    last = None
    for attempt in range(settings.retries + 1):
        try:
            r = session.get(url, timeout=settings.timeout, allow_redirects=True)
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  ! сеть: не удалось получить {url}: {last}")
    return None


def _next_page_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Ищет ссылку 'следующая страница' в битриксовой пагинации."""
    # типичные классы битрикса: modern-page-next, flex-pagination ...
    a = soup.select_one(
        "a.modern-page-next, .pagination a[rel=next], a[title*=Следующая], "
        ".bx-pag-next a, a.flex-pagination-next"
    )
    if a and a.get("href"):
        href = a["href"]
        if href.startswith("http"):
            return href
        return base_url + href
    return None


def fetch_page_products(session: requests.Session, settings: Settings, path: str,
                        max_pages: int = 50) -> List[Product]:
    """Тянет страницу и все её страницы пагинации, парсит товары."""
    url = path if path.startswith("http") else f"{settings.base_url}{path}"
    collected: List[Product] = []
    seen_urls = set()
    pages = 0
    while url and pages < max_pages and url not in seen_urls:
        seen_urls.add(url)
        resp = _get(session, url, settings)
        if resp is None:
            break
        products = parse_products(resp.text)
        print(f"  стр.{pages + 1}: {len(products)} позиций  ({url})")
        collected.extend(products)
        soup = BeautifulSoup(resp.text, "lxml")
        url = _next_page_url(soup, settings.base_url)
        pages += 1
        if url:
            time.sleep(0.5)  # вежливая пауза между страницами
    return collected


def fetch_all(session: requests.Session, settings: Settings) -> List[Product]:
    """Собирает товары со всех заданных бланков (и каталога как резерв)."""
    all_products: List[Product] = []
    for path in settings.blank_paths:
        print(f"Бланк: {path}")
        all_products.extend(fetch_page_products(session, settings, path))

    if not all_products and settings.catalog_path:
        print(f"Бланк пуст — пробую каталог: {settings.catalog_path}")
        all_products.extend(fetch_page_products(session, settings, settings.catalog_path))

    return _dedupe(all_products)


def _dedupe(products: List[Product]) -> List[Product]:
    seen = set()
    out = []
    for p in products:
        key = (p.article.lower(), p.name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
