"""Сессия и авторизация на 1С-Битрикс портале b2b-jac.com.

Поддерживает два режима (см. дизайн-док, раздел 3):
  1) логин + пароль  -> POST формы /?login=yes
  2) импорт cookie    -> подстановка готовой сессии из браузера
"""
from __future__ import annotations

import re
import time
from http.cookies import SimpleCookie
from typing import Optional

import requests

from .config import Settings


class AuthError(RuntimeError):
    """Не удалось авторизоваться / нет учётных данных."""


# --- Детекторы состояния авторизации (тестируются на фикстурах, без сети) ---

_LOGIN_FORM_RE = re.compile(r'name=["\']?(USER_PASSWORD|AUTH_FORM)["\']?', re.IGNORECASE)
_AUTH_FAIL_RE = re.compile(
    r"(Неверный логин или пароль|Неправильный логин|неверный пароль|"
    r"заблокирован|captcha|Введите слово на картинке)",
    re.IGNORECASE,
)
_AUTH_OK_RE = re.compile(
    r"(logout=yes|/auth/\?logout|Выйти|Выход из|personal|Личный кабинет|Мои заказы)",
    re.IGNORECASE,
)


def auth_failed(html: str) -> bool:
    return bool(_AUTH_FAIL_RE.search(html or ""))


def looks_authenticated(html: str) -> bool:
    """Эвристика: страница отдана залогиненному пользователю.

    Признан авторизованным, если есть явный маркер ЛК/выхода ИЛИ на странице
    нет формы логина и нет сообщения об ошибке авторизации.
    """
    h = html or ""
    if _AUTH_FAIL_RE.search(h):
        return False
    if _AUTH_OK_RE.search(h):
        return True
    # нет формы логина на «защищённой» странице -> считаем, что вошли
    return not _LOGIN_FORM_RE.search(h)


def build_login_payload(login: str, password: str, backurl: str = "/") -> dict:
    """Тело POST для битриксовой формы авторизации."""
    return {
        "AUTH_FORM": "Y",
        "TYPE": "AUTH",
        "backurl": backurl,
        "USER_LOGIN": login,
        "USER_PASSWORD": password,
        "USER_REMEMBER": "Y",
        "Login": "Войти",
    }


def _apply_cookie_string(session: requests.Session, cookie_str: str, domain: str) -> None:
    """Разбирает строку 'a=b; c=d' и кладёт cookie в сессию."""
    jar = SimpleCookie()
    jar.load(cookie_str)
    for key, morsel in jar.items():
        session.cookies.set(key, morsel.value, domain=domain)
    # запасной разбор (SimpleCookie капризен к некоторым именам)
    for pair in cookie_str.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and k not in session.cookies:
                session.cookies.set(k, v, domain=domain)


def new_session(settings: Settings) -> requests.Session:
    s = requests.Session()
    # игнорируем системный/песочничный прокси — ходим напрямую на любой машине
    s.trust_env = False
    s.headers.update({
        "User-Agent": settings.user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    return s


def _get(session: requests.Session, url: str, settings: Settings, **kw) -> requests.Response:
    last = None
    for attempt in range(settings.retries + 1):
        try:
            return session.get(url, timeout=settings.timeout, **kw)
        except requests.RequestException as e:  # таймаут/сеть
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise AuthError(f"Сетевая ошибка при запросе {url}: {last}")


def _domain(settings: Settings) -> str:
    host = re.sub(r"^https?://", "", settings.base_url).split("/")[0]
    return host.split(":")[0]  # без порта (для cookie-домена)


def authenticate(settings: Settings) -> requests.Session:
    """Возвращает авторизованную сессию или бросает AuthError."""
    problem = settings.credentials_problem()
    if problem:
        raise AuthError(problem)

    session = new_session(settings)
    domain = _domain(settings)

    # Режим 2: готовая cookie из браузера
    if settings.cookie.strip():
        _apply_cookie_string(session, settings.cookie, domain)
        if verify_session(session, settings):
            return session
        raise AuthError(
            "Переданный JAC_COOKIE не даёт авторизованную сессию (возможно истёк). "
            "Обнови cookie из браузера или используй логин+пароль."
        )

    # Режим 1: логин + пароль
    login_url = f"{settings.base_url}/?login=yes"
    _get(session, login_url, settings)  # получить свежий PHPSESSID
    payload = build_login_payload(settings.login, settings.password)
    try:
        resp = session.post(login_url, data=payload, timeout=settings.timeout,
                            allow_redirects=True)
    except requests.RequestException as e:
        raise AuthError(f"Сетевая ошибка при логине: {e}")

    if auth_failed(resp.text):
        raise AuthError(
            "Портал ответил «Неверный логин или пароль». Проверь JAC_LOGIN/JAC_PASSWORD "
            "в config/.env. Подбор логина не делается во избежание блокировки."
        )

    if not verify_session(session, settings):
        raise AuthError(
            "Логин отправлен, но сессия не подтвердилась. Запусти команду `discover`, "
            "чтобы сохранить ответ портала для диагностики."
        )
    return session


def verify_session(session: requests.Session, settings: Settings) -> bool:
    """Проверяет, что под этой сессией доступна защищённая страница (бланк)."""
    path = settings.blank_paths[0] if settings.blank_paths else "/"
    url = f"{settings.base_url}{path}"
    resp = _get(session, url, settings, allow_redirects=True)
    # если нас перекинуло на форму логина — не авторизованы
    if "login=yes" in resp.url and _LOGIN_FORM_RE.search(resp.text):
        return False
    return looks_authenticated(resp.text)
