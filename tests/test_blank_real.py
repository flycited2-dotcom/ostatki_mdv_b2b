"""Тест парсера на РЕАЛЬНОЙ верстке бланка заказа b2b-jac.com (фикстура из дампа)."""
from pathlib import Path

from jac_scraper.parse import parse_products

FIXTURE = Path(__file__).parent / "fixtures" / "blank_real_sample.html"


def _parse():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_products(html, category="Бытовые сплит-системы")


def test_three_products():
    assert len(_parse()) == 3


def test_price_is_your_price_not_rrc():
    p = {x.article: x for x in _parse()}
    # "Ваша цена" (дилерская), НЕ РРЦ (26 000)
    assert p["EKSA-20HN / EKOA-20HN"].price == 12360.0
    assert p["EKSA-25HN / EKOA-25HN"].price == 13470.0
    assert p["EKSA-35HN / EKOA-35HN"].price == 18970.0


def test_stock_from_nalichie():
    p = {x.article: x for x in _parse()}
    assert p["EKSA-20HN / EKOA-20HN"].stock_qty == 0
    assert p["EKSA-20HN / EKOA-20HN"].stock_raw == "0 шт"
    assert p["EKSA-35HN / EKOA-35HN"].stock_qty == 69


def test_attributes_capture_rrc_and_warehouses():
    p = {x.article: x for x in _parse()}
    a = p["EKSA-35HN / EKOA-35HN"].attributes
    assert a["РРЦ"] == "37 000 ₽"
    assert a["Холод, кВт"] == "3.65"
    assert a["Москва (ОП АЯК - Крым)"] == "Больше 50"  # текстовый остаток сохранён


def test_category_and_identity():
    for x in _parse():
        assert x.category == "Бытовые сплит-системы"
        assert x.article == x.name          # модель = идентификатор
        assert x.source == "jac_b2b"
