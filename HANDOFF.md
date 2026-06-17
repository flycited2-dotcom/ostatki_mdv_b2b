# HANDOFF — JAC B2B scraper (osatakti_mdv_b2b)

**Дата:** 2026-06-17. Контекст/архитектура — в `README.md` и
`docs/superpowers/specs/2026-06-16-jac-b2b-scraper-design.md`. Здесь: что это,
что работает, нюансы портала, деплой, открытые пункты.

## Что это

Скрапер B2B-портала поставщика **JAC** (https://b2b-jac.com, 1С-Битрикс) — у него
нет API (в отличие от 3 других поставщиков). Собирает остатки, цены, бренд, серию
и характеристики (ТТХ) по технике (кондиционеры) и кладёт в JSON, который читает
Telegram-бот SplitHome (`Site_ostatki_api_teleram`) как **4-го поставщика**.

Стек: Python 3.13, `requests` + `BeautifulSoup` (без браузера). Тесты: `pytest`
(35, офлайн, вкл. сквозной мок-портал).

## Статус: РАБОТАЕТ ✅

Проверено на живом портале: **526 позиций**, 526/526 с брендом, **511 моделей с
ТТХ**. Логин в `config/.env` (gitignored).

## Команды

```powershell
python -m venv .venv ; .\.venv\Scripts\python -m pip install -r requirements.txt
copy config\.env.example config\.env   # вписать JAC_LOGIN (или JAC_COOKIE)
.\run_scrape.ps1 check        # проверить вход
.\run_scrape.ps1              # scrape -> data\jac_stock_{ГГГГММДД,latest}.{csv,json,xlsx}
.\.venv\Scripts\python -m jac_scraper specs   # ТТХ карточек -> data\jac_specs_latest.json
.\.venv\Scripts\python -m pytest -q
```

`run_scrape.ps1 [check|discover|scrape|specs]` — обёртка (UTF-8, логи, NO_PROXY).

## Данные на выходе (для бота)

- `data/jac_stock_latest.json` — список товаров: `article` (модель), `name`,
  `brand` (MDV/EUROKLIMAT/THAICON/Mitsubishi Heavy), `series`, `price` («Ваша
  цена» = опт), `stock_qty`/`stock_raw` («Наличие»), `category`, `path`,
  `attributes` (РРЦ, Холод кВт, склады **Крым**/**Москва**…).
- `data/jac_specs_latest.json` — `{артикул: {brand, series, characteristics{77 полей}}}`.

## Нюансы портала (важно — на этом терялись данные)

- Авторизация: Битрикс-форма POST `/?login=yes` (`USER_LOGIN`/`USER_PASSWORD`,
  `AUTH_FORM=Y`, `TYPE=AUTH`). Логин — e-mail, в `config/.env`.
- Корень `/orders/blank_zakaza/` товаров НЕ отдаёт — только дерево категорий.
  Товары в 4 верхних категориях (Бытовые `000000002`, Мульти `000000032`,
  Полупром `000000070`, Аксессуары `000000125`); каждая агрегирует свой подраздел.
- **Пагинация:** ОБЯЗАТЕЛЬНО `?PAGEN_1=N&SIZEN_1=10` в КАЖДОМ запросе. Без явных
  параметров Битрикс помнит страницу в сессии → страницы после ~10-й приходят
  пустыми. Перелёт за последнюю страницу возвращает НЕ пусто → число страниц
  берём из пагинации (`_max_page`), а не по «пустой странице».
- **Бренд/серия** — из `data-href` товара (путь категории), карта путь→имя из
  дерева; БЕЗ обхода карточек. Запасной бренд — по префиксу модели
  (MD→MDV, EK→EUROKLIMAT, TL→THAICON, SRK/SCM→Mitsubishi Heavy).
- **Цена-колонки** помечены `data-code`: РРЦ и «ТЛТ ООО» (= «Ваша цена», опт).
  Парсер берёт «Ваша цена» по заголовку, РРЦ кладёт в `attributes`.
- **ТТХ** — карточка товара (тот же `path`), блок `bzd-props__table` (вкл. скрытые
  строки). `specs` кэш-ориентирован: первый прогон ~500 карточек, дальше только
  новые модели (`--refresh` — заново).
- Сеть: на машине разработки системный SOCKS-прокси ломает Python — в коде
  `session.trust_env=False`, в скриптах `NO_PROXY=*`.

## Архитектура (jac_scraper/)

`config.py` (.env) · `session.py` (логин/cookie) · `catalog.py` (обход категорий,
пагинация, бренд/серия) · `parse.py` (бланк → Product, классы `product__property--*`) ·
`specs.py` (ТТХ карточек) · `discover.py` (калибровка) · `export.py` (csv/json/xlsx) ·
`models.py` (Product) · `cli.py` (`check`/`discover`/`scrape`/`specs`).

## Деплой (рекомендация)

Скрапер — чистый `requests`, идёт и на Linux-VPS рядом с ботом. Cron до 09:00 МСК:
`scrape` затем `specs` (кэш → дёшев), пути файлов прописать в `.env` бота
(`JAC_STOCK_JSON`, `JAC_SPECS_JSON`). Логин JAC — в `config/.env` скрапера.

## Открытые пункты

- УТП серий — РЕАЛИЗОВАНО. Команды `utp-collect` (сбор кандидатов с сайтов
  вендоров в `data/jac_utp_candidates.xlsx`) → ручная вычитка галочками в колонке
  «Брать» → `utp-build` (финал `data/jac_utp_latest.json`). Автосбор по MDV /
  THAICON / Mitsubishi Heavy; EUROKLIMAT УТП на сайте не публикует — вписывать
  вручную в xlsx. Подробности и таблица охвата — в README, раздел «УТП серий».
  Контракт для бота: читать `data/jac_utp_latest.json` и брать
  `utp[brand][normalize_series(series)]` (ключ серии — UPPER CASE без лишних пробелов).
- Серии у части полупром/мультисплит — это тип («Сплит-системы канального типа»),
  а не модельная линейка (так в дереве портала). При желании — донастроить.
- Репозиторий создан локально; удалённый GitHub-remote добавить при передаче.
