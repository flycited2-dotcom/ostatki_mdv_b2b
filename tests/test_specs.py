from jac_scraper.specs import parse_characteristics

CARD = """<html><body>
<h2>Технические характеристики модели EKSA-20HN</h2>
<table class="bzd-props__table table table-striped">
  <tr class="bzd-props__table-row">
    <td class="bzd-props__table-col">Тип управления компрессором</td>
    <td class="bzd-props__table-col">on-off</td></tr>
  <tr class="bzd-props__table-row">
    <td class="bzd-props__table-col">Холод, кВт</td>
    <td class="bzd-props__table-col">2.2</td></tr>
  <tr class="bzd-props__table-row toggle-row d-none">
    <td class="bzd-props__table-col">Тип хладагента</td>
    <td class="bzd-props__table-col">R410A</td></tr>
  <tr class="bzd-props__table-row toggle-row d-none">
    <td class="bzd-props__table-col">Бренд</td>
    <td class="bzd-props__table-col">Euroklimat</td></tr>
</table></body></html>"""


def test_parse_characteristics_includes_hidden_rows():
    ch = parse_characteristics(CARD)
    assert ch["Тип управления компрессором"] == "on-off"
    assert ch["Холод, кВт"] == "2.2"
    assert ch["Тип хладагента"] == "R410A"     # строка скрыта (d-none) — всё равно берём
    assert ch["Бренд"] == "Euroklimat"
    assert len(ch) == 4


def test_parse_characteristics_empty():
    assert parse_characteristics("") == {}
    assert parse_characteristics("<html><body>нет таблицы</body></html>") == {}
