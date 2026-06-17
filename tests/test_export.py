import csv
import json
from pathlib import Path

from jac_scraper.models import Product
from jac_scraper.export import export_all


def _sample():
    return [
        Product(article="JAC-1001", name="Фильтр", brand="JAC",
                stock_qty=12, stock_raw="12", price=1250.5, unit="шт"),
        Product(article="JAC-1002", name="Колодки", brand="JAC",
                stock_qty=None, stock_raw="много", price=3480.0, unit="компл"),
    ]


def test_export_csv_json_xlsx(tmp_path: Path):
    written = export_all(_sample(), tmp_path, ["csv", "json", "xlsx"])
    assert len(written) == 3
    for p in written:
        assert p.exists() and p.stat().st_size > 0


def test_csv_content(tmp_path: Path):
    export_all(_sample(), tmp_path, ["csv"])
    csv_file = next(tmp_path.glob("*.csv"))
    with csv_file.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0][0] == "Артикул/Модель"
    assert rows[1][0] == "JAC-1001"
    assert "1250.5" in rows[1]


def test_json_content(tmp_path: Path):
    export_all(_sample(), tmp_path, ["json"])
    json_file = next(tmp_path.glob("*.json"))
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["article"] == "JAC-1001"
    assert data[1]["stock_raw"] == "много"
    assert data[0]["source"] == "jac_b2b"
