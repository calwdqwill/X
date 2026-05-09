"""
Утилиты: логирование, задержки, retry-декоратор, работа с датами.
"""

import asyncio
import functools
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from config import settings

F = TypeVar("F", bound=Callable[..., Any])


# ==========================================
# Логирование
# ==========================================

def setup_logging() -> logging.Logger:
    """Настраивает корневой логгер: консоль + файл с ротацией по дате."""
    logger = logging.getLogger("x_hybrid_poster")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # На Windows принудительно переключаем консоль в UTF-8
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Вывод в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Вывод в файл
    log_file = Path("logs") / f"{datetime.utcnow().strftime('%Y-%m-%d')}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Глобальный логгер для импорта
logger = setup_logging()


# ==========================================
# Задержки (human-like)
# ==========================================

async def async_delay(min_sec: int, max_sec: int) -> None:
    """Асинхронная пауза со случайной длительностью в диапазоне [min_sec, max_sec]."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug("Задержка %.1f сек (%d–%d)", delay, min_sec, max_sec)
    await asyncio.sleep(delay)


def sync_delay(min_sec: int, max_sec: int) -> None:
    """Синхронная пауза со случайной длительностью в диапазоне [min_sec, max_sec]."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug("Синхронная задержка %.1f сек (%d–%d)", delay, min_sec, max_sec)
    import time
    time.sleep(delay)


# ==========================================
# Retry декоратор
# ==========================================

def retry(
    max_retries: int = 3,
    exceptions: tuple = (Exception,),
    backoff_base: float = 2.0,
    max_backoff: float = 120.0,
) -> Callable[[F], F]:
    """Декоратор для повторных попыток с экспоненциальным backoff."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    wait = min(backoff_base ** attempt, max_backoff)
                    logger.warning(
                        "[%s] Попытка %d/%d не удалась: %s. Повтор через %.1f сек...",
                        func.__name__,
                        attempt,
                        max_retries,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
            raise last_exception  # type: ignore[misc]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    wait = min(backoff_base ** attempt, max_backoff)
                    logger.warning(
                        "[%s] Попытка %d/%d не удалась: %s. Повтор через %.1f сек...",
                        func.__name__,
                        attempt,
                        max_retries,
                        exc,
                        wait,
                    )
                    import time
                    time.sleep(wait)
            raise last_exception  # type: ignore[misc]

        # Возвращаем async или sync версию в зависимости от типа функции
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ==========================================
# Трекинг стоимости
# ==========================================

class CostTracker:
    """Простой трекер расходов на публикации."""

    def __init__(self, cost_per_post_usd: float = 0.015):
        self.cost_per_post = cost_per_post_usd
        self.total_posts = 0
        self.total_cost = 0.0

    def add_post(self, count: int = 1) -> None:
        """Увеличивает счётчик опубликованных постов и стоимость."""
        self.total_posts += count
        self.total_cost += self.cost_per_post * count
        logger.info(
            "Трекинг стоимости: +%d пост(а) = $%.4f. Итого: %d постов, $%.4f",
            count,
            self.cost_per_post * count,
            self.total_posts,
            self.total_cost,
        )


def get_today_start() -> datetime:
    """Возвращает начало текущих суток по UTC."""
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def truncate_text(text: str, max_length: int = 280) -> str:
    """Обрезает текст до лимита X (280 символов по умолчанию), добавляя '…'."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
