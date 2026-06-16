from pathlib import Path

from jac_scraper.parse import parse_products, detect_column_map

FIXTURE = Path(__file__).parent / "fixtures" / "blank_zakaza_sample.html"


def _load():
    return FIXTURE.read_text(encoding="utf-8")


def test_detect_column_map():
    headers = ["Артикул", "Наименование", "Бренд", "Наличие", "Цена", "Ед."]
    cmap = detect_column_map(headers)
    assert cmap["article"] == 0
    assert cmap["name"] == 1
    assert cmap["brand"] == 2
    assert cmap["stock"] == 3
    assert cmap["price"] == 4
    assert cmap["unit"] == 5


def test_parse_blank_extracts_four_products():
    products = parse_products(_load())
    # 4 товара; строка ИТОГО должна быть отброшена
    assert len(products) == 4
    names = [p.name for p in products]
    assert "ИТОГО" not in names


def test_parse_values():
    products = {p.article: p for p in parse_products(_load())}

    p1 = products["JAC-1001"]
    assert p1.name == "Фильтр масляный JAC N56"
    assert p1.brand == "JAC"
    assert p1.stock_qty == 12
    assert p1.price == 1250.50
    assert p1.unit == "шт"

    p2 = products["JAC-1002"]
    assert p2.stock_qty is None          # "много" -> текст
    assert p2.stock_raw == "много"
    assert p2.price == 3480.0

    p3 = products["JAC-1003"]
    assert p3.stock_raw == "под заказ"
    assert p3.price == 2100.0

    p4 = products["JAC-1004"]
    assert p4.stock_qty == 0             # ноль остаток — валиден
    assert p4.brand == "NGK"


def test_all_products_have_source():
    for p in parse_products(_load()):
        assert p.source == "jac_b2b"
        assert p.scraped_at
