from jac_scraper.models import normalize_number, parse_stock, Product


def test_normalize_russian_format():
    assert normalize_number("1 250,50 руб.") == 1250.50
    assert normalize_number("3 480 руб.") == 3480.0
    assert normalize_number("540,00 руб.") == 540.0


def test_normalize_thousands_and_decimal():
    assert normalize_number("1.234,00") == 1234.0   # 1.234,00 -> 1234.00
    assert normalize_number("1,234.50") == 1234.50   # англ. формат
    assert normalize_number("12 345") == 12345.0


def test_normalize_empty_and_dash():
    assert normalize_number("") is None
    assert normalize_number("—") is None
    assert normalize_number(None) is None


def test_parse_stock_numeric_and_text():
    qty, raw = parse_stock("12")
    assert qty == 12 and raw == "12"
    qty, raw = parse_stock("много")
    assert qty is None and raw == "много"
    qty, raw = parse_stock("под заказ")
    assert qty is None and raw == "под заказ"
    qty, raw = parse_stock("0")
    assert qty == 0 and raw == "0"


def test_product_validity():
    assert Product(article="A1", price=10).is_valid()
    assert Product(name="Длинное имя", stock_raw="много").is_valid()
    assert not Product().is_valid()
    assert not Product(name="ab").is_valid()  # нет ни цены, ни остатка
