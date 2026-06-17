# УТП по сериям — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать с сайтов производителей маркетинговые УТП по сериям в редактируемый Excel, дать владельцу отметить нужные галочкой и собрать финальный `data/jac_utp_latest.json` для бота.

**Architecture:** Новый модуль `jac_scraper/utp.py` (каркас: нормализация/сопоставление серий, запись xlsx-кандидатов, сборка финального json) + `jac_scraper/utp_sites.py` (один общий экстрактор УТП с конфигом под каждый бренд, калибруемый на сохранённых HTML). Две CLI-подкоманды: `utp-collect` (сбор кандидатов) и `utp-build` (сборка финала). Сеть и стиль — как в существующем скрапере (`trust_env=False`, BeautifulSoup+lxml, json-кэш).

**Tech Stack:** Python 3, requests, beautifulsoup4 + lxml, openpyxl, pytest.

**Спека:** [2026-06-17-utp-series-collector-design.md](../specs/2026-06-17-utp-series-collector-design.md)

**Контракт с ботом:** ключ серии в `jac_utp_latest.json` — нормализованное имя серии (верхний регистр, схлопнутые пробелы). Бот для товара берёт `utp[brand][normalize_series(product.series)]`.

---

## Структура файлов

- Create: `jac_scraper/utp.py` — каркас: `normalize_series`, `match_series`, `UtpCandidate`, запись `jac_utp_candidates.xlsx`/`.json`, чтение отмеченного xlsx → `jac_utp_latest.json`, отчёт о пробелах покрытия.
- Create: `jac_scraper/utp_sites.py` — `extract_utp(html, cfg)` (общий экстрактор), `BRAND_CONFIGS` (конфиг на бренд), `collect_brand(session, settings, cfg)` (обход страниц серий бренда).
- Modify: `jac_scraper/cli.py` — добавить подкоманды `utp-collect` и `utp-build`.
- Test: `tests/test_utp.py` — нормализация, сопоставление, xlsx round-trip, сборка финала.
- Test: `tests/test_utp_sites.py` — `extract_utp` на сохранённых фикстурах брендов.
- Fixtures: `tests/fixtures/utp_<brand>_series.html` — сохранённые реальные страницы серий (по одной на бренд для старта).

---

## Task 1: Нормализация и сопоставление серий

**Files:**
- Create: `jac_scraper/utp.py`
- Test: `tests/test_utp.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_utp.py
from jac_scraper.utp import normalize_series, match_series


def test_normalize_series_uppercase_and_spaces():
    assert normalize_series("  Integra   pro  ") == "INTEGRA PRO"
    assert normalize_series("aurora on/off r32") == "AURORA ON/OFF R32"
    assert normalize_series("") == ""
    assert normalize_series(None) == ""


def test_match_series_direct_and_alias():
    candidate_index = {"INTEGRA PRO": "Integra Pro", "AURORA": "Aurora"}
    # прямое совпадение
    assert match_series("integra pro", candidate_index) == "Integra Pro"
    # через alias (JAC пишет иначе, чем сайт)
    aliases = {"AURORA ON/OFF R32": "AURORA"}
    assert match_series("Aurora ON/OFF R32", candidate_index, aliases) == "Aurora"
    # нет совпадения
    assert match_series("НЕИЗВЕСТНАЯ", candidate_index) is None
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python -m pytest tests/test_utp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jac_scraper.utp'`

- [ ] **Step 3: Минимальная реализация**

```python
# jac_scraper/utp.py
"""УТП по сериям: каркас сбора кандидатов и сборки финального файла.

Поток (см. дизайн-док):
  utp-collect -> data/jac_utp_candidates.xlsx (+ .json бэкап)
  владелец ставит галочки в колонке «Брать»
  utp-build   -> data/jac_utp_latest.json {бренд: {СЕРИЯ_НОРМ: [УТП...]}}
"""
from __future__ import annotations

from dataclasses import dataclass


def normalize_series(name: str) -> str:
    """Верхний регистр + схлопывание пробелов. Ключ для связки JAC <-> сайт."""
    return " ".join((name or "").upper().split())


def match_series(jac_series: str, candidate_index: dict, aliases: dict | None = None) -> str | None:
    """Возвращает оригинальное имя серии сайта для серии JAC или None.

    candidate_index: {НОРМ_имя_серии_сайта: оригинальное_имя_сайта}
    aliases: {НОРМ_имя_серии_JAC: НОРМ_имя_серии_сайта} — для расхождений написания
    """
    aliases = aliases or {}
    key = normalize_series(jac_series)
    key = aliases.get(key, key)
    return candidate_index.get(key)
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest tests/test_utp.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/utp.py tests/test_utp.py
git commit -m "feat(utp): нормализация и сопоставление серий"
```

---

## Task 2: Запись xlsx-кандидатов и json-бэкапа

**Files:**
- Modify: `jac_scraper/utp.py`
- Test: `tests/test_utp.py`

- [ ] **Step 1: Написать падающий тест**

```python
# добавить в tests/test_utp.py
from pathlib import Path
from jac_scraper.utp import UtpCandidate, write_candidates


def test_write_candidates_xlsx_and_json(tmp_path: Path):
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
    # первая строка данных
    assert [ws.cell(row=2, column=i).value for i in range(1, 5)] == ["MDV", "INTEGRA", 1, "3D Air Flow"]
    assert ws.cell(row=2, column=5).value is None  # колонка «Брать» пустая
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python -m pytest tests/test_utp.py::test_write_candidates_xlsx_and_json -v`
Expected: FAIL — `ImportError: cannot import name 'UtpCandidate'`

- [ ] **Step 3: Минимальная реализация (добавить в `jac_scraper/utp.py`)**

```python
import json
from pathlib import Path
from typing import List

CANDIDATES_XLSX = "jac_utp_candidates.xlsx"
CANDIDATES_JSON = "jac_utp_candidates.json"
LATEST_JSON = "jac_utp_latest.json"

CANDIDATES_HEADER = ["Бренд", "Серия", "№", "Текст УТП", "Брать"]


@dataclass
class UtpCandidate:
    brand: str
    series: str
    text: str


def write_candidates(cands: List[UtpCandidate], xlsx_path: Path, json_path: Path) -> None:
    """Пишет кандидатов в xlsx (с пустой колонкой «Брать») и json-бэкап.
    Строки отсортированы по бренду -> серии; нумерация № в пределах серии.
    """
    from openpyxl import Workbook

    cands = sorted(cands, key=lambda c: (c.brand, c.series))
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "УТП кандидаты"
    ws.append(CANDIDATES_HEADER)
    n_by_series: dict = {}
    for c in cands:
        key = (c.brand, c.series)
        n_by_series[key] = n_by_series.get(key, 0) + 1
        ws.append([c.brand, c.series, n_by_series[key], c.text, None])
    widths = [18, 28, 5, 70, 8]
    for col_idx, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = w
    wb.save(xlsx_path)

    json_path.write_text(
        json.dumps([c.__dict__ for c in cands], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest tests/test_utp.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/utp.py tests/test_utp.py
git commit -m "feat(utp): запись кандидатов в xlsx и json"
```

---

## Task 3: Сборка финального json из отмеченного xlsx

**Files:**
- Modify: `jac_scraper/utp.py`
- Test: `tests/test_utp.py`

- [ ] **Step 1: Написать падающий тест**

```python
# добавить в tests/test_utp.py
from jac_scraper.utp import build_latest_from_xlsx


def test_build_latest_only_marked_rows(tmp_path: Path):
    # готовим xlsx руками: 3 строки, отмечены 1-я и 3-я
    from openpyxl import Workbook
    from jac_scraper.utp import CANDIDATES_HEADER
    wb = Workbook(); ws = wb.active
    ws.append(CANDIDATES_HEADER)
    ws.append(["MDV", "Integra", 1, "3D Air Flow", "x"])
    ws.append(["MDV", "Integra", 2, "Мусорный пункт", None])
    ws.append(["MDV", "Aurora", 1, "Компактный корпус", "1"])
    xlsx_path = tmp_path / "in.xlsx"; wb.save(xlsx_path)

    out_path = tmp_path / "jac_utp_latest.json"
    result = build_latest_from_xlsx(xlsx_path, out_path)

    # ключ серии — нормализованный; взяты только отмеченные строки
    assert result == {
        "MDV": {"INTEGRA": ["3D Air Flow"], "AURORA": ["Компактный корпус"]}
    }
    import json as _j
    assert _j.loads(out_path.read_text(encoding="utf-8")) == result
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python -m pytest tests/test_utp.py::test_build_latest_only_marked_rows -v`
Expected: FAIL — `ImportError: cannot import name 'build_latest_from_xlsx'`

- [ ] **Step 3: Минимальная реализация (добавить в `jac_scraper/utp.py`)**

```python
def build_latest_from_xlsx(xlsx_path: Path, out_path: Path) -> dict:
    """Читает отмеченный xlsx, берёт строки с непустой «Брать»,
    группирует в {бренд: {СЕРИЯ_НОРМ: [тексты в порядке файла]}} и пишет json."""
    from openpyxl import load_workbook

    ws = load_workbook(xlsx_path, read_only=True).active
    rows = ws.iter_rows(min_row=2, values_only=True)
    out: dict = {}
    for row in rows:
        if not row or len(row) < 5:
            continue
        brand, series, _num, text, take = row[0], row[1], row[2], row[3], row[4]
        if take is None or str(take).strip() == "" or not text:
            continue
        skey = normalize_series(str(series))
        out.setdefault(str(brand), {}).setdefault(skey, []).append(str(text).strip())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest tests/test_utp.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/utp.py tests/test_utp.py
git commit -m "feat(utp): сборка финального json из отмеченного xlsx"
```

---

## Task 4: Общий экстрактор УТП + конфиг брендов (на фикстуре)

**Files:**
- Create: `jac_scraper/utp_sites.py`
- Create: `tests/fixtures/utp_mdv_series.html` (сохранённая реальная страница серии MDV — см. шаг 1)
- Test: `tests/test_utp_sites.py`

- [ ] **Step 1: Сохранить реальную фикстуру MDV (калибровка)**

Найти URL страницы одной серии MDV (например INTEGRA) на mdv-aircond.ru и сохранить её HTML в фикстуру:

```bash
python -c "import requests; s=requests.Session(); s.trust_env=False; \
open('tests/fixtures/utp_mdv_series.html','w',encoding='utf-8').write(\
s.get('https://mdv-aircond.ru/catalog/integra/', timeout=30, \
headers={'User-Agent':'Mozilla/5.0'}).text)"
```

Открыть сохранённый файл, найти блок преимуществ/особенностей (заголовок «Преимущества»/«Особенности» и список `<li>` либо карточки фич). Записать одну реально присутствующую фразу — она пойдёт в тест ниже как `KNOWN_PHRASE`.

- [ ] **Step 2: Написать падающий тест**

```python
# tests/test_utp_sites.py
from pathlib import Path
from jac_scraper.utp_sites import extract_utp, BRAND_CONFIGS

FIX = Path(__file__).parent / "fixtures"

# ВАЖНО: подставить реально присутствующую в фикстуре фразу (см. Task 4 шаг 1)
KNOWN_PHRASE = "3D Air Flow"


def test_extract_utp_mdv_fixture():
    html = (FIX / "utp_mdv_series.html").read_text(encoding="utf-8")
    items = extract_utp(html, BRAND_CONFIGS["MDV"])
    assert isinstance(items, list)
    assert any(KNOWN_PHRASE.lower() in s.lower() for s in items)
    # без мусора: пункты непустые и разумной длины
    assert all(s.strip() for s in items)
    assert all(len(s) <= 400 for s in items)


def test_extract_utp_empty():
    assert extract_utp("", BRAND_CONFIGS["MDV"]) == []
    assert extract_utp("<html><body>нет блока</body></html>", BRAND_CONFIGS["MDV"]) == []
```

- [ ] **Step 3: Запустить тест — убедиться, что падает**

Run: `python -m pytest tests/test_utp_sites.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jac_scraper.utp_sites'`

- [ ] **Step 4: Реализация — общий экстрактор + конфиг (откалибровать по фикстуре)**

Базовая эвристика: внутри секции, чей заголовок/класс содержит ключевые слова преимуществ, собрать тексты пунктов списка/карточек. `cfg["selectors"]` уточняется по реальной фикстуре из шага 1.

```python
# jac_scraper/utp_sites.py
"""Сбор УТП по сериям с сайтов производителей.

Один общий экстрактор + конфиг под каждый бренд (вместо 4 отдельных парсеров).
Селекторы калибруются на сохранённых фикстурах (tests/fixtures/utp_<brand>_series.html).
"""
from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

# Ключевые слова заголовков блоков преимуществ (нижний регистр)
_ADV_WORDS = ("преимущест", "особенност", "почему", "достоинств")
_MIN_LEN, _MAX_LEN = 3, 400


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def extract_utp(html: str, cfg: dict) -> List[str]:
    """HTML страницы серии -> список текстов УТП. cfg["selectors"] — CSS-селекторы
    блоков преимуществ для конкретного бренда (определяются по фикстуре)."""
    soup = BeautifulSoup(html or "", "lxml")
    out: List[str] = []
    seen = set()

    nodes = []
    for sel in cfg.get("selectors", []):
        nodes.extend(soup.select(sel))
    # фолбэк: секции с «преимущества/особенности» в заголовке
    if not nodes:
        for h in soup.find_all(["h2", "h3"]):
            if any(w in h.get_text().lower() for w in _ADV_WORDS):
                sib = h.find_next(["ul", "ol", "div"])
                if sib:
                    nodes.append(sib)

    for node in nodes:
        items = node.select("li") or node.select(cfg.get("item_selector", "li"))
        for it in items:
            t = _clean(it.get_text(" "))
            if _MIN_LEN <= len(t) <= _MAX_LEN and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return out


BRAND_CONFIGS = {
    "MDV": {
        "base_url": "https://mdv-aircond.ru",
        "selectors": [],   # заполнить по фикстуре Task 4
        "item_selector": "li",
    },
    "THAICON": {
        "base_url": "https://thaicon-climate.com",
        "selectors": [],   # Task 5
        "item_selector": "li",
    },
    "Mitsubishi Heavy": {
        "base_url": "https://mhi-aircond.ru",
        "selectors": [],   # Task 5
        "item_selector": "li",
    },
    "EUROKLIMAT": {
        "base_url": "https://euroklimat.com.ru",
        "selectors": [],   # Task 5
        "item_selector": "li",
    },
}
```

После написания — открыть фикстуру, проставить рабочие CSS-селекторы в `BRAND_CONFIGS["MDV"]["selectors"]`, чтобы тест прошёл (если фолбэк уже ловит — оставить `selectors` пустым).

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `python -m pytest tests/test_utp_sites.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Коммит**

```bash
git add jac_scraper/utp_sites.py tests/test_utp_sites.py tests/fixtures/utp_mdv_series.html
git commit -m "feat(utp): общий экстрактор УТП + конфиг MDV на фикстуре"
```

---

## Task 5: Калибровка остальных брендов (THAICON, Mitsubishi Heavy, EUROKLIMAT)

**Files:**
- Modify: `jac_scraper/utp_sites.py` (`selectors` в `BRAND_CONFIGS`)
- Create: `tests/fixtures/utp_thaicon_series.html`, `utp_mhi_series.html`, `utp_euroklimat_series.html`
- Test: `tests/test_utp_sites.py`

- [ ] **Step 1: Сохранить фикстуры (по странице серии на каждый бренд)**

```bash
python -c "import requests; s=requests.Session(); s.trust_env=False; h={'User-Agent':'Mozilla/5.0'}; \
open('tests/fixtures/utp_thaicon_series.html','w',encoding='utf-8').write(s.get('https://thaicon-climate.com/catalog/phantom-inverter/', timeout=30, headers=h).text)"
# аналогично для mhi-aircond.ru и euroklimat.com.ru — URL уточнить из каталога сайта
```

- [ ] **Step 2: Написать падающие тесты (по фразе из каждой фикстуры)**

```python
# добавить в tests/test_utp_sites.py
import pytest

@pytest.mark.parametrize("brand,fixture,phrase", [
    ("THAICON", "utp_thaicon_series.html", "ПОДСТАВИТЬ_ФРАЗУ_THAICON"),
    ("Mitsubishi Heavy", "utp_mhi_series.html", "ПОДСТАВИТЬ_ФРАЗУ_MHI"),
    ("EUROKLIMAT", "utp_euroklimat_series.html", "ПОДСТАВИТЬ_ФРАЗУ_EK"),
])
def test_extract_utp_other_brands(brand, fixture, phrase):
    html = (FIX / fixture).read_text(encoding="utf-8")
    items = extract_utp(html, BRAND_CONFIGS[brand])
    assert any(phrase.lower() in s.lower() for s in items)
```

Подставить реально присутствующие фразы из сохранённых фикстур.

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `python -m pytest tests/test_utp_sites.py::test_extract_utp_other_brands -v`
Expected: FAIL (фразы не найдены / селекторы пустые)

- [ ] **Step 4: Откалибровать `selectors` для трёх брендов**

Открыть каждую фикстуру, найти блок преимуществ, проставить CSS-селекторы в соответствующий `BRAND_CONFIGS[brand]["selectors"]`. Для EUROKLIMAT, если УТП на странице нет, оставить `selectors: []` и пометить в логе как «нет кандидатов» (владелец допишет руками в xlsx — это предусмотрено спекой).

- [ ] **Step 5: Запустить — убедиться, что проходит (где УТП есть)**

Run: `python -m pytest tests/test_utp_sites.py -v`
Expected: PASS для брендов с УТП. Если у EUROKLIMAT кандидатов нет — соответствующий тест помечается `pytest.mark.skip("нет УТП на сайте, ручной ввод")`.

- [ ] **Step 6: Коммит**

```bash
git add jac_scraper/utp_sites.py tests/test_utp_sites.py tests/fixtures/utp_*.html
git commit -m "feat(utp): калибровка THAICON/MHI/EUROKLIMAT"
```

---

## Task 6: Обход страниц серий бренда (сбор кандидатов по сети)

**Files:**
- Modify: `jac_scraper/utp_sites.py`
- Test: `tests/test_utp_sites.py`

Сбор по сети не тестируем офлайн напрямую; тестируем чистую функцию разбора списка серий из HTML каталога.

- [ ] **Step 1: Написать падающий тест на разбор списка серий**

```python
# добавить в tests/test_utp_sites.py
from jac_scraper.utp_sites import parse_series_links

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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest tests/test_utp_sites.py::test_parse_series_links -v`
Expected: FAIL — `cannot import name 'parse_series_links'`

- [ ] **Step 3: Реализация (добавить в `jac_scraper/utp_sites.py`)**

```python
import time
from urllib.parse import urljoin


def parse_series_links(html: str, cfg: dict) -> dict:
    """HTML каталога -> {имя_серии: абсолютный_url} по cfg["series_link_selector"]."""
    soup = BeautifulSoup(html or "", "lxml")
    out: dict = {}
    for a in soup.select(cfg.get("series_link_selector", "")):
        name = _clean(a.get_text(" "))
        href = a.get("href", "")
        if name and href:
            out[name] = urljoin(cfg["base_url"], href)
    return out


def collect_brand(session, settings, brand: str, cfg: dict):
    """Обходит каталог бренда -> страницы серий -> УТП. Возвращает list[UtpCandidate]."""
    from .utp import UtpCandidate

    catalog_url = urljoin(cfg["base_url"], cfg.get("catalog_path", "/catalog/"))
    cands = []
    try:
        cat_html = session.get(catalog_url, timeout=settings.timeout).text
    except Exception as e:  # сеть — не валим весь прогон
        print(f"  ! {brand}: каталог недоступен ({e})")
        return cands
    series_links = parse_series_links(cat_html, cfg)
    print(f"  {brand}: серий найдено {len(series_links)}")
    for name, url in series_links.items():
        try:
            html = session.get(url, timeout=settings.timeout).text
        except Exception as e:
            print(f"  ! {brand}/{name}: {e}")
            continue
        for text in extract_utp(html, cfg):
            cands.append(UtpCandidate(brand=brand, series=name, text=text))
        time.sleep(0.35)
    return cands
```

Добавить в каждый `BRAND_CONFIGS[brand]` ключи `catalog_path` и `series_link_selector` (откалибровать по сайту).

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python -m pytest tests/test_utp_sites.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/utp_sites.py tests/test_utp_sites.py
git commit -m "feat(utp): обход каталога и страниц серий бренда"
```

---

## Task 7: Отчёт о покрытии (какие серии JAC без УТП)

**Files:**
- Modify: `jac_scraper/utp.py`
- Test: `tests/test_utp.py`

- [ ] **Step 1: Написать падающий тест**

```python
# добавить в tests/test_utp.py
from jac_scraper.utp import coverage_gaps


def test_coverage_gaps():
    jac_series = {"MDV": ["INTEGRA", "Aurora", "Сплит-система настенного типа"]}
    candidates = [UtpCandidate("MDV", "Integra", "x")]
    type_words = ("сплит-система", "канальн", "кассетн", "мульти")
    gaps = coverage_gaps(jac_series, candidates, type_words)
    # INTEGRA покрыта; AURORA — пробел; «настенного типа» — это тип, не серия (пропуск)
    assert gaps == {"MDV": ["AURORA"]}
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest tests/test_utp.py::test_coverage_gaps -v`
Expected: FAIL — `cannot import name 'coverage_gaps'`

- [ ] **Step 3: Реализация (добавить в `jac_scraper/utp.py`)**

```python
def coverage_gaps(jac_series: dict, candidates: List["UtpCandidate"],
                  type_words: tuple) -> dict:
    """Возвращает {бренд: [СЕРИИ_НОРМ без УТП]}, исключая серии-типы.
    jac_series: {бренд: [имена серий JAC]}; candidates: собранные УТП-кандидаты."""
    have = {}
    for c in candidates:
        have.setdefault(c.brand, set()).add(normalize_series(c.series))
    gaps: dict = {}
    for brand, names in jac_series.items():
        brand_have = have.get(brand, set())
        missing = []
        for raw in names:
            norm = normalize_series(raw)
            if not norm or any(w in raw.lower() for w in type_words):
                continue  # пустое имя или тип, не модельная серия
            if norm not in brand_have and norm not in missing:
                missing.append(norm)
        if missing:
            gaps[brand] = missing
    return gaps
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python -m pytest tests/test_utp.py -v`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/utp.py tests/test_utp.py
git commit -m "feat(utp): отчёт о пробелах покрытия серий"
```

---

## Task 8: CLI-подкоманды utp-collect и utp-build

**Files:**
- Modify: `jac_scraper/cli.py`

- [ ] **Step 1: Реализация — функции команд (добавить в `jac_scraper/cli.py`)**

Импорт вверху файла:

```python
from .utp import (
    UtpCandidate, write_candidates, build_latest_from_xlsx, coverage_gaps,
    CANDIDATES_XLSX, CANDIDATES_JSON, LATEST_JSON,
)
from .utp_sites import BRAND_CONFIGS, collect_brand
```

Функции команд:

```python
_TYPE_WORDS = ("сплит-система", "канальн", "кассетн", "мульти", "колонн", "напольн")


def cmd_utp_collect(settings) -> int:
    """Обходит сайты вендоров, собирает УТП-кандидаты, пишет xlsx для вычитки."""
    from .session import new_session
    session = new_session(settings)

    cands = []
    for brand, cfg in BRAND_CONFIGS.items():
        cands.extend(collect_brand(session, settings, brand, cfg))
    if not cands:
        print("[utp-collect] ✗ кандидатов не собрано — проверь селекторы в BRAND_CONFIGS.")
        return 3

    xlsx_path = settings.output_dir / CANDIDATES_XLSX
    json_path = settings.output_dir / CANDIDATES_JSON
    write_candidates(cands, xlsx_path, json_path)
    print(f"[utp-collect] ✓ кандидатов {len(cands)} → {xlsx_path}")

    # отчёт о пробелах по сериям из последнего jac_stock_latest.json
    stock_file = settings.output_dir / "jac_stock_latest.json"
    if stock_file.exists():
        products = json.loads(stock_file.read_text(encoding="utf-8"))
        jac_series: dict = {}
        for p in products:
            jac_series.setdefault(p.get("brand", ""), [])
            s = p.get("series", "")
            if s and s not in jac_series[p.get("brand", "")]:
                jac_series[p.get("brand", "")].append(s)
        gaps = coverage_gaps(jac_series, cands, _TYPE_WORDS)
        if gaps:
            print("[utp-collect] серии JAC без УТП (допиши руками в xlsx при необходимости):")
            for brand, names in gaps.items():
                print(f"  {brand}: {', '.join(names)}")
    return 0


def cmd_utp_build(settings) -> int:
    """Собирает финальный jac_utp_latest.json из отмеченного xlsx."""
    xlsx_path = settings.output_dir / CANDIDATES_XLSX
    if not xlsx_path.exists():
        print(f"[utp-build] ✗ нет {xlsx_path}. Сначала запусти `utp-collect`.")
        return 3
    out_path = settings.output_dir / LATEST_JSON
    result = build_latest_from_xlsx(xlsx_path, out_path)
    total = sum(len(v) for series in result.values() for v in series.values())
    print(f"[utp-build] ✓ серий {sum(len(s) for s in result.values())}, "
          f"УТП {total} → {out_path}")
    return 0
```

- [ ] **Step 2: Зарегистрировать подкоманды в `build_parser()` и `main()`**

В `build_parser()` добавить:

```python
    sub.add_parser("utp-collect", help="собрать УТП-кандидаты с сайтов вендоров в xlsx")
    sub.add_parser("utp-build", help="собрать финальный jac_utp_latest.json из отмеченного xlsx")
```

В `main()` расширить словарь диспетчеризации:

```python
    return {
        "check": cmd_check,
        "discover": cmd_discover,
        "scrape": cmd_scrape,
        "utp-collect": cmd_utp_collect,
        "utp-build": cmd_utp_build,
    }[args.command](settings)
```

- [ ] **Step 3: Проверить, что CLI парсится и команды видны**

Run: `python -m jac_scraper --help`
Expected: в списке команд присутствуют `utp-collect` и `utp-build`.

- [ ] **Step 4: Прогнать весь тест-набор**

Run: `python -m pytest -q`
Expected: все тесты проходят (включая прежние).

- [ ] **Step 5: Коммит**

```bash
git add jac_scraper/cli.py
git commit -m "feat(utp): CLI-команды utp-collect и utp-build"
```

---

## Task 9: Живой прогон и документация

**Files:**
- Modify: `README.md`, `HANDOFF.md`

- [ ] **Step 1: Живой сбор кандидатов**

Run: `python -m jac_scraper utp-collect`
Expected: создан `data/jac_utp_candidates.xlsx`, в консоли число кандидатов и список серий-пробелов. Открыть xlsx, проверить осмысленность текстов; при необходимости подправить `selectors` в `BRAND_CONFIGS` и перезапустить.

- [ ] **Step 2: Проверить сборку финала**

Поставить пару галочек `x` в колонке «Брать», затем:
Run: `python -m jac_scraper utp-build`
Expected: создан `data/jac_utp_latest.json` только с отмеченными УТП, ключи серий — в верхнем регистре.

- [ ] **Step 3: Обновить README и HANDOFF**

В `README.md` — добавить раздел про команды `utp-collect`/`utp-build` и формат `jac_utp_latest.json`. В `HANDOFF.md` — заменить открытый пункт про УТП (строка ~80) на описание готового процесса и контракт ключа серии для бота (`utp[brand][normalize_series(series)]`).

- [ ] **Step 4: Коммит**

```bash
git add README.md HANDOFF.md
git commit -m "docs(utp): команды сбора УТП и контракт файла для бота"
```

---

## Зависимости задач

- Task 1 → 2 → 3: каркас `utp.py` (последовательно, общий файл).
- Task 4 → 5 → 6: сайтовые экстракторы `utp_sites.py` (последовательно).
- Task 7: дополняет `utp.py` (после Task 3).
- Task 8: связывает всё (после 6 и 7).
- Task 9: живой прогон и доки (последний).
