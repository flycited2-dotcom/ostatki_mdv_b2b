from jac_scraper.session import (
    build_login_payload, auth_failed, looks_authenticated, _apply_cookie_string,
)
import requests

LOGIN_FORM_HTML = """
<form name="form_auth" method="post" action="/?login=yes">
  <input type="hidden" name="AUTH_FORM" value="Y" />
  <input type="text" name="USER_LOGIN" />
  <input type="password" name="USER_PASSWORD" />
</form>
"""

FAIL_HTML = LOGIN_FORM_HTML + "<div class='errortext'>Неверный логин или пароль.</div>"

AUTH_HTML = """
<div><a href="/personal/">Личный кабинет</a>
<a href="/?logout=yes">Выйти</a></div>
<h1>Бланк заказа</h1>
"""


def test_build_login_payload():
    p = build_login_payload("user", "pass")
    assert p["AUTH_FORM"] == "Y"
    assert p["TYPE"] == "AUTH"
    assert p["USER_LOGIN"] == "user"
    assert p["USER_PASSWORD"] == "pass"
    assert p["Login"] == "Войти"


def test_auth_failed_detects_error():
    assert auth_failed(FAIL_HTML)
    assert not auth_failed(AUTH_HTML)


def test_looks_authenticated():
    assert looks_authenticated(AUTH_HTML)
    assert not looks_authenticated(LOGIN_FORM_HTML)   # есть форма логина
    assert not looks_authenticated(FAIL_HTML)         # ошибка авторизации


def test_apply_cookie_string():
    s = requests.Session()
    _apply_cookie_string(s, "PHPSESSID=abc123; BITRIX_SM_LOGIN=ivan", "b2b-jac.com")
    assert s.cookies.get("PHPSESSID") == "abc123"
    assert s.cookies.get("BITRIX_SM_LOGIN") == "ivan"
