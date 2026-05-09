"""
APScheduler для периодического запуска цикла fetch → process → generate → post.
Интервал рандомизируется (20–30 мин) для естественности.
"""

import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from utils import logger


class CycleScheduler:
    """Планировщик, который запускает основной цикл с заданным интервалом."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self._job_id = "x_cycle"

    def start(self, cycle_callback) -> None:
        """
        Запускает планировщик с рандомным интервалом.

        Args:
            cycle_callback: Корутина или функция, которая выполняет один полный цикл.
        """
        interval_minutes = random.randint(
            settings.scheduler_interval_min,
            settings.scheduler_interval_max,
        )

        self.scheduler.add_job(
            cycle_callback,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self._job_id,
            replace_existing=True,
            max_instances=1,  # не запускать новый цикл, пока старый не завершился
        )

        self.scheduler.start()
        logger.info(
            "Планировщик запущен с интервалом %d минут",
            interval_minutes,
        )

    def shutdown(self) -> None:
        """Останавливает планировщик gracefully."""
        self.scheduler.shutdown(wait=True)
        logger.info("Планировщик остановлен")
