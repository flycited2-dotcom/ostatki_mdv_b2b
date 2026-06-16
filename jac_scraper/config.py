"""Загрузка и валидация настроек из config/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "config" / ".env"


@dataclass
class Settings:
    base_url: str
    login: str
    password: str
    cookie: str
    blank_paths: List[str]
    catalog_path: str
    output_dir: Path
    output_formats: List[str]
    timeout: int
    retries: int
    user_agent: str

    @property
    def has_credentials(self) -> bool:
        return bool(self.cookie.strip()) or bool(self.login.strip() and self.password.strip())

    def credentials_problem(self) -> str:
        """Возвращает текст проблемы с учётками или '' если всё ок."""
        if self.cookie.strip():
            return ""
        if not self.login.strip():
            return (
                "Не задан JAC_LOGIN. Впиши логин от B2B-портала в config/.env "
                "(пароль уже подставлен), либо вставь JAC_COOKIE из браузера."
            )
        if not self.password.strip():
            return "Не задан JAC_PASSWORD в config/.env."
        return ""


def _split_csv(value: str) -> List[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def load_settings(env_path: Path | None = None) -> Settings:
    path = Path(env_path) if env_path else ENV_PATH
    load_dotenv(path, override=True)

    base_url = os.getenv("JAC_BASE_URL", "https://b2b-jac.com").rstrip("/")
    output_dir = PROJECT_ROOT / os.getenv("JAC_OUTPUT_DIR", "data")

    return Settings(
        base_url=base_url,
        login=os.getenv("JAC_LOGIN", "").strip(),
        password=os.getenv("JAC_PASSWORD", "").strip(),
        cookie=os.getenv("JAC_COOKIE", "").strip(),
        blank_paths=_split_csv(os.getenv("JAC_BLANK_PATHS", "/orders/blank_zakaza/000000002/")),
        catalog_path=os.getenv("JAC_CATALOG_PATH", "/catalog/").strip(),
        output_dir=output_dir,
        output_formats=_split_csv(os.getenv("JAC_OUTPUT_FORMATS", "csv,json")) or ["csv", "json"],
        timeout=int(os.getenv("JAC_TIMEOUT", "30")),
        retries=int(os.getenv("JAC_RETRIES", "2")),
        user_agent=os.getenv(
            "JAC_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        ),
    )
