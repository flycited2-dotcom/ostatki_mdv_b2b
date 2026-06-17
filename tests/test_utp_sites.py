from pathlib import Path

from jac_scraper.utp_sites import extract_utp, BRAND_CONFIGS

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
