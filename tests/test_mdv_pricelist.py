from pathlib import Path

from openpyxl import Workbook

from jac_scraper.mdv_pricelist import (
    clean_series_label, build_jac_index, map_to_jac, parse_mdv_pricelist,
)


def test_clean_series_label():
    assert clean_series_label("INTEGRA ON/OFF, R32 (снято с производства)") == "INTEGRA ON/OFF R32"
    assert clean_series_label("CLASSIC INVERTER, R32") == "CLASSIC INVERTER R32"


def _jac_index(*series):
    return build_jac_index([{"brand": "MDV", "series": s} for s in series], "MDV")


def test_map_to_jac_longest_token_match():
    idx = _jac_index("INTEGRA", "INTEGRA PRO", "iERA INVERTER")
    # длиннейшее совпадение: PRO бьёт просто INTEGRA
    assert map_to_jac("INTEGRA PRO ERP Full DC INVERTER R32", idx) == "INTEGRA PRO"
    # инверторная INTEGRA -> JAC "INTEGRA"
    assert map_to_jac("INTEGRA INVERTER DC INVERTER R32", idx) == "INTEGRA"
    # токены JAC-имени вкраплены не подряд — всё равно матч
    assert map_to_jac("iERA ERP Full DC INVERTER R32", idx) == "iERA INVERTER"
    # нет соответствия
    assert map_to_jac("NOVA 3-IN-1 ERP", idx) is None


def test_parse_mdv_pricelist(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "RAC on-off"          # должен быть из PRICELIST_SHEETS
    ws.append(["Модель"])                                   # r1 — шапка
    ws.append(["INTEGRA ON/OFF, R32"])                      # r2 — заголовок серии
    ws.append(["● класс А\n● Wi-Fi", "● 3D Airflow"])       # r3 — УТП (cols A,B)
    ws.append(["MDSAI-07HRN8"])                             # r4 — модель
    ws.append(["НЕИЗВЕСТНАЯ СЕРИЯ X"])                       # r5 — заголовок без JAC
    ws.append(["● что-то"])                                 # r6 — УТП несопоставимой серии
    path = tmp_path / "price.xlsx"
    wb.save(path)

    idx = _jac_index("INTEGRA ON/OFF R32", "INTEGRA PRO")
    cands, unmapped = parse_mdv_pricelist(path, idx)

    assert all(c.brand == "MDV" for c in cands)
    assert {c.series for c in cands} == {"INTEGRA ON/OFF R32"}
    assert [c.text for c in cands] == ["класс А", "Wi-Fi", "3D Airflow"]
    assert unmapped == ["НЕИЗВЕСТНАЯ СЕРИЯ X"]
