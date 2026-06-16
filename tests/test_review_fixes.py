"""Регрессионные тесты на баги, найденные при код-ревью."""
from jac_scraper.models import normalize_number
from jac_scraper.parse import detect_column_map, parse_products, dedupe
from jac_scraper.models import Product


# --- H3: точка как разделитель тысяч в рус. ценах ---
def test_dot_thousands_not_treated_as_decimal():
    assert normalize_number("1.250") == 1250        # было 1.25
    assert normalize_number("10.000") == 10000      # было 10.0
    assert normalize_number("1.234.567") == 1234567
    assert normalize_number("1.250 руб.") == 1250


def test_real_decimals_preserved():
    assert normalize_number("1250.50") == 1250.50
    assert normalize_number("540.00") == 540.0
    assert normalize_number("12.5") == 12.5
    assert normalize_number("1 250,50 руб.") == 1250.50  # рус. с запятой
    assert normalize_number("1.250,50") == 1250.50       # точка-тысячи + запятая


# --- H1: "Номенклатура" не должна красть колонку под article ---
def test_nomenklatura_maps_to_name_not_article():
    cmap = detect_column_map(["Номенклатура", "Остаток", "Цена"])
    assert cmap.get("name") == 0
    assert "article" not in cmap
    assert cmap.get("stock") == 1
    assert cmap.get("price") == 2


# --- M2: "Сумма руб." не должна стать колонкой цены вместо "Цена" ---
def test_summa_rub_does_not_steal_price():
    cmap = detect_column_map(["Артикул", "Наименование", "Сумма руб.", "Цена"])
    assert cmap.get("article") == 0
    assert cmap.get("name") == 1
    assert cmap.get("price") == 3   # настоящая "Цена", а не "Сумма руб."


# --- M3: "Штрихкод" не должен попасть в article через подстроку "код" ---
def test_barcode_not_mapped_as_article():
    cmap = detect_column_map(["Штрихкод", "Наименование", "Цена"])
    assert "article" not in cmap
    assert cmap.get("name") == 1
    assert cmap.get("price") == 2


def test_plain_kod_still_maps_to_article():
    cmap = detect_column_map(["Код", "Наименование", "Цена"])
    assert cmap.get("article") == 0


# --- M4: дедуп не схлопывает разные товары без артикула ---
def test_dedupe_keeps_distinct_when_article_empty():
    items = [
        Product(name="Колодки", brand="JAC", price=100.0),
        Product(name="Колодки", brand="NGK", price=200.0),  # другой бренд/цена
    ]
    assert len(dedupe(items)) == 2


def test_dedupe_collapses_true_duplicates():
    items = [
        Product(article="A1", name="Фильтр", price=100.0),
        Product(article="A1", name="Фильтр", price=100.0),
    ]
    assert len(dedupe(items)) == 1


# --- H1 сквозной: таблица с одной колонкой-наименованием ---
SINGLE_NAME_HTML = """<table>
<tr><th>Номенклатура</th><th>Наличие</th><th>Цена</th></tr>
<tr><td>Фильтр масляный JAC</td><td>5</td><td>1.250 руб.</td></tr>
</table>"""


def test_single_name_column_keeps_name_and_price():
    products = parse_products(SINGLE_NAME_HTML)
    assert len(products) == 1
    p = products[0]
    assert p.name == "Фильтр масляный JAC"
    assert p.article == ""          # отдельной колонки артикула нет
    assert p.price == 1250          # H3: 1.250 -> 1250, не 1.25
    assert p.stock_qty == 5
