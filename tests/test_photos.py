"""Тесты сборки карты фото серий (jac_scraper/photos.py) — чистые функции, без сети."""
from jac_scraper.photos import (
    normalize_series, export_photo_map, match_photo, build_brand_photos,
)


def test_normalize_series():
    assert normalize_series('  Integra   Pro ') == 'INTEGRA PRO'
    assert normalize_series(None) == ''
    assert normalize_series('') == ''


def test_export_photo_map_first_wins_and_skips_empty():
    items = [
        {'SECTIONS': {'SECTION_3': 'OP Inverter'}, 'PREVIEW_PICTURE': 'http://x/op1.png'},
        {'SECTIONS': {'SECTION_3': 'OP Inverter'}, 'PREVIEW_PICTURE': 'http://x/op2.png'},
        {'SECTIONS': {'SECTION_3': 'Aurora R32 On/Off'}, 'PREVIEW_PICTURE': 'http://x/a.png'},
        {'SECTIONS': {'SECTION_3': 'No Photo'}, 'PREVIEW_PICTURE': ''},
        {'SECTIONS': {}, 'PREVIEW_PICTURE': 'http://x/z.png'},
    ]
    m = export_photo_map(items)
    assert m['OP INVERTER'] == 'http://x/op1.png'          # первый выигрывает
    assert m['AURORA R32 ON/OFF'] == 'http://x/a.png'
    assert 'NO PHOTO' not in m                              # пустое фото пропущено
    assert len(m) == 2


def test_match_exact():
    m = {'CLASSIC INVERTER': 'http://x/c.png'}
    assert match_photo('Classic Inverter', m) == 'http://x/c.png'


def test_match_token_order_insensitive():
    m = {'AURORA R32 ON/OFF': 'http://x/a.png'}
    assert match_photo('AURORA ON/OFF R32', m) == 'http://x/a.png'   # тот же набор токенов


def test_match_ambiguous_below_threshold_returns_none():
    m = {'INTEGRA PRO': 'p', 'INTEGRA INVERTER': 'i', 'INTEGRA ON/OFF': 'o'}
    assert match_photo('INTEGRA', m) is None     # 0.5 и неоднозначно — не ставим рискованное фото


def test_match_override_wins():
    m = {'SRK-ZSPR-S STANDARD': 'http://x/s.png'}
    assert match_photo('STANDARD', m, overrides={'STANDARD': 'SRK-ZSPR-S STANDARD'}) == 'http://x/s.png'


def test_build_brand_photos_only_instock_and_matched():
    stock = ['CLASSIC INVERTER', 'AURORA ON/OFF R32', 'UNKNOWN SERIES']
    m = {'CLASSIC INVERTER': 'c', 'AURORA R32 ON/OFF': 'a'}
    out = build_brand_photos(stock, m, overrides={})
    assert out == {'CLASSIC INVERTER': 'c', 'AURORA ON/OFF R32': 'a'}   # неизвестная серия отброшена
