from jac_scraper.utp import normalize_series, match_series


def test_normalize_series_uppercase_and_spaces():
    assert normalize_series("  Integra   pro  ") == "INTEGRA PRO"
    assert normalize_series("aurora on/off r32") == "AURORA ON/OFF R32"
    assert normalize_series("") == ""
    assert normalize_series(None) == ""


def test_match_series_direct_and_alias():
    candidate_index = {"INTEGRA PRO": "Integra Pro", "AURORA": "Aurora"}
    assert match_series("integra pro", candidate_index) == "Integra Pro"
    aliases = {"AURORA ON/OFF R32": "AURORA"}
    assert match_series("Aurora ON/OFF R32", candidate_index, aliases) == "Aurora"
    assert match_series("НЕИЗВЕСТНАЯ", candidate_index) is None
