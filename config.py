"""
Конфигурация приложения через Pydantic Settings.
Все секреты и настройки читаются из .env файла.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Главный класс настроек. Все поля валидируются при старте."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- X/Twitter Официальное API (tweepy) ---
    x_api_bearer: str = Field(..., description="Bearer token для X API v2")
    x_api_key: str = Field(..., description="API Key для OAuth 1.0a")
    x_api_secret: str = Field(..., description="API Secret для OAuth 1.0a")
    x_access_token: str = Field(..., description="Access Token пользователя")
    x_access_secret: str = Field(..., description="Access Secret пользователя")

    # --- Twikit (неофициальное чтение) ---
    twikit_username: str = Field(..., description="Логин от X")
    twikit_email: str = Field(..., description="Email от X (для прохождения доп. проверок)")
    twikit_password: str = Field(..., description="Пароль от X")
    twikit_cookies_path: str = Field("./cookies.json", description="Путь к файлу с cookies twikit")

    # --- LLM API ---
    llm_api_key: str = Field(..., description="API ключ для LLM")
    llm_base_url: str = Field("https://api.openai.com/v1", description="Base URL LLM провайдера")
    llm_model: str = Field("gpt-4o-mini", description="Название модели")

    # --- База данных ---
    db_path: str = Field("./x_hybrid.db", description="Путь к SQLite БД")

    # --- Лимиты и задержки ---
    post_daily_limit: int = Field(5, description="Максимум постов в сутки")
    post_per_run_limit: int = Field(3, description="Максимум постов за один запуск цикла")

    fetch_delay_min: int = Field(8, description="Минимальная задержка между read-операциями (сек)")
    fetch_delay_max: int = Field(25, description="Максимальная задержка между read-операциями (сек)")

    post_delay_min: int = Field(40, description="Минимальная задержка между публикациями (сек)")
    post_delay_max: int = Field(180, description="Максимальная задержка между публикациями (сек)")

    scheduler_interval_min: int = Field(20, description="Минимальный интервал планировщика (мин)")
    scheduler_interval_max: int = Field(30, description="Максимальный интервал планировщика (мин)")

    # --- Сеть ---
    http_proxy: Optional[str] = Field(None, description="HTTP/HTTPS прокси для twikit (формат: http://user:pass@host:port)")

    # --- Прочее ---
    dry_run: bool = Field(False, description="Режим сухого прогона (без реальной публикации)")
    log_level: str = Field("INFO", description="Уровень логирования")
    vision_path: str = Field("./vision.md", description="Путь к файлу видения")

    @property
    def db_url(self) -> str:
        """Формирует SQLAlchemy-compatible URL для SQLite."""
        return f"sqlite:///{self.db_path}"


# Глобальный инстанс настроек, который импортируется во все модули
settings = Settings()
