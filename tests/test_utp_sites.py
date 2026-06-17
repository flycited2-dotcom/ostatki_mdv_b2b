import pytest
from pathlib import Path

from jac_scraper.utp_sites import extract_utp, BRAND_CONFIGS, parse_series_links

FIX = Path(__file__).parent / "fixtures"

KNOWN_PHRASE = "3D Air Flow"


def test_extract_utp_mdv_fixture():
    html = (FIX / "utp_mdv_series.html").read_text(encoding="utf-8")
    items = extract_utp(html, BRAND_CONFIGS["MDV"])
    assert isinstance(items, list)
    assert any(KNOWN_PHRASE.lower() in s.lower() for s in items)
    assert all(s.strip() for s in items)
    assert all(len(s) <= 400 for s in items)


def test_extract_utp_empty():
    assert extract_utp("", BRAND_CONFIGS["MDV"]) == []
    assert extract_utp("<html><body>нет блока</body></html>", BRAND_CONFIGS["MDV"]) == []


CATALOG = """<html><body>
<a class="series-card" href="/catalog/integra/">INTEGRA</a>
<a class="series-card" href="/catalog/aurora/">AURORA</a>
<a href="/about/">О нас</a>
</body></html>"""


def test_parse_series_links():
    cfg = {"base_url": "https://mdv-aircond.ru", "series_link_selector": "a.series-card"}
    links = parse_series_links(CATALOG, cfg)
    assert links == {
        "INTEGRA": "https://mdv-aircond.ru/catalog/integra/",
        "AURORA": "https://mdv-aircond.ru/catalog/aurora/",
    }


@pytest.mark.parametrize("brand,fixture,phrase", [
    ("THAICON", "utp_thaicon_series.html", "Full DC-Inverter"),
    ("Mitsubishi Heavy", "utp_mhi_series.html", "Очень тихие"),
    pytest.param(
        "EUROKLIMAT", "utp_euroklimat_series.html", "нет УТП",
        marks=pytest.mark.skip(reason="нет УТП на сайте EUROKLIMAT, ручной ввод"),
    ),
])
def test_extract_utp_other_brands(brand, fixture, phrase):
    html = (FIX / fixture).read_text(encoding="utf-8")
    items = extract_utp(html, BRAND_CONFIGS[brand])
    assert any(phrase.lower() in s.lower() for s in items)
