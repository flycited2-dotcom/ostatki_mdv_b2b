from pathlib import Path

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


def test_write_candidates_xlsx_and_json(tmp_path: Path):
    from jac_scraper.utp import UtpCandidate, write_candidates

    cands = [
        UtpCandidate(brand="MDV", series="INTEGRA", text="3D Air Flow"),
        UtpCandidate(brand="MDV", series="INTEGRA", text="Wi-Fi управление"),
        UtpCandidate(brand="THAICON", series="PHANTOM", text="Тихий режим"),
    ]
    xlsx_path = tmp_path / "jac_utp_candidates.xlsx"
    json_path = tmp_path / "jac_utp_candidates.json"
    write_candidates(cands, xlsx_path, json_path)

    assert xlsx_path.exists() and json_path.exists()

    from openpyxl import load_workbook
    ws = load_workbook(xlsx_path).active
    header = [c.value for c in ws[1]]
    assert header == ["Бренд", "Серия", "№", "Текст УТП", "Брать"]
    assert [ws.cell(row=2, column=i).value for i in range(1, 5)] == ["MDV", "INTEGRA", 1, "3D Air Flow"]
    assert ws.cell(row=2, column=5).value is None
