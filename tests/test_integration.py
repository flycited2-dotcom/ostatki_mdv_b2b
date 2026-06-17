"""Сквозной тест против локального мок-портала Битрикса.

Поднимает крошечный HTTP-сервер, имитирующий:
  - форму логина /?login=yes (GET) + проверку логина (POST)
  - защищённый бланк заказа с пагинацией (2 страницы)
и прогоняет реальный код: authenticate() -> fetch_all() -> export_all().
Сети наружу нет.
"""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest

from jac_scraper.config import Settings
from jac_scraper.session import authenticate
from jac_scraper.catalog import fetch_all
from jac_scraper.export import export_all

GOOD_LOGIN, GOOD_PASS = "dealer42", "secret"

LOGIN_FORM = """<html><body>
<form name="form_auth" method="post" action="/?login=yes">
<input type="hidden" name="AUTH_FORM" value="Y"/>
<input type="text" name="USER_LOGIN"/>
<input type="password" name="USER_PASSWORD"/>
</form></body></html>"""

FAIL_PAGE = LOGIN_FORM + "<div>Неверный логин или пароль.</div>"

PAGE1 = """<html><body>
<a href="/?logout=yes">Выйти</a>
<table><tr><th>Артикул</th><th>Наименование</th><th>Наличие</th><th>Цена</th></tr>
<tr><td>JAC-1001</td><td>Фильтр масляный</td><td>12</td><td>1 250,50 руб.</td></tr>
<tr><td>JAC-1002</td><td>Колодки тормозные</td><td>много</td><td>3 480 руб.</td></tr>
</table>
<a class="modern-page-next" href="/orders/blank_zakaza/000000002/?PAGEN_1=2">Следующая</a>
</body></html>"""

PAGE2 = """<html><body>
<a href="/?logout=yes">Выйти</a>
<table><tr><th>Артикул</th><th>Наименование</th><th>Наличие</th><th>Цена</th></tr>
<tr><td>JAC-2001</td><td>Ремень ГРМ</td><td>под заказ</td><td>2 100,00 руб.</td></tr>
<tr><td>JAC-2002</td><td>Свеча зажигания</td><td>0</td><td>540,00 руб.</td></tr>
</table></body></html>"""

_AUTHED: set = set()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # тише в тестах
        pass

    def _sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if part.strip().startswith("PHPSESSID="):
                return part.strip().split("=", 1)[1]
        return None

    def _send(self, body: str, set_sid: str | None = None, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if set_sid:
            self.send_header("Set-Cookie", f"PHPSESSID={set_sid}; path=/")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        sid = self._sid()
        set_sid = None
        if not sid:
            sid = uuid.uuid4().hex
            set_sid = sid

        if parsed.path == "/" and "login=yes" in (parsed.query or ""):
            return self._send(LOGIN_FORM, set_sid)

        if parsed.path.startswith("/orders/blank_zakaza"):
            if sid in _AUTHED:
                page = parse_qs(parsed.query).get("PAGEN_1", ["1"])[0]
                return self._send(PAGE2 if page == "2" else PAGE1, set_sid)
            return self._send(LOGIN_FORM, set_sid)  # не авторизован -> форма

        return self._send(LOGIN_FORM, set_sid)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        sid = self._sid() or uuid.uuid4().hex
        login = params.get("USER_LOGIN", [""])[0]
        pw = params.get("USER_PASSWORD", [""])[0]
        if login == GOOD_LOGIN and pw == GOOD_PASS:
            _AUTHED.add(sid)
            return self._send(PAGE1, sid)  # как будто пустили внутрь
        return self._send(FAIL_PAGE, sid)


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _settings(base_url: str, tmp_path: Path, **over) -> Settings:
    defaults = dict(
        base_url=base_url, login=GOOD_LOGIN, password=GOOD_PASS, cookie="",
        blank_paths=["/orders/blank_zakaza/000000002/"], catalog_path="/catalog/",
        output_dir=tmp_path, output_formats=["csv", "json"], timeout=10, retries=1,
        user_agent="test-agent",
    )
    defaults.update(over)
    return Settings(**defaults)


def test_end_to_end_scrape(server, tmp_path):
    settings = _settings(server, tmp_path)
    session = authenticate(settings)              # реальный логин-POST + verify
    products = fetch_all(session, settings)        # 2 страницы пагинации
    arts = sorted(p.article for p in products)
    assert arts == ["JAC-1001", "JAC-1002", "JAC-2001", "JAC-2002"]

    written = export_all(products, tmp_path, settings.output_formats)
    assert len(written) == 3   # csv, json + стабильный jac_stock_latest.json
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    by_art = {d["article"]: d for d in data}
    assert by_art["JAC-1001"]["price"] == 1250.5
    assert by_art["JAC-1001"]["stock_qty"] == 12
    assert by_art["JAC-2001"]["stock_raw"] == "под заказ"
    assert by_art["JAC-2002"]["stock_qty"] == 0


def test_wrong_password_raises(server, tmp_path):
    from jac_scraper.session import AuthError
    settings = _settings(server, tmp_path, password="wrong")
    with pytest.raises(AuthError) as e:
        authenticate(settings)
    assert "Неверный" in str(e.value) or "логин" in str(e.value)


def test_cookie_mode(server, tmp_path):
    # Сначала логинимся по паролю, забираем cookie, потом ходим только по cookie.
    s1 = authenticate(_settings(server, tmp_path))
    sid = s1.cookies.get("PHPSESSID")
    settings = _settings(server, tmp_path, login="", password="",
                        cookie=f"PHPSESSID={sid}")
    session = authenticate(settings)
    products = fetch_all(session, settings)
    assert len(products) == 4
