"""
Публикация постов ТОЛЬКО через официальный X API v2 (tweepy).
Здесь нет риска бана за публикацию — используем легальный API.
"""

import random
from typing import Optional

import tweepy

from config import settings
from utils import logger, retry, sync_delay


class XPoster:
    """Обертка над tweepy Client для публикации твитов с учётом лимитов."""

    COST_PER_POST_USD = 0.015

    def __init__(self, dry_run: bool = False) -> None:
        # OAuth 1.0a User Context — необходим для write-операций (create_tweet)
        self.client = tweepy.Client(
            consumer_key=settings.x_api_key,
            consumer_secret=settings.x_api_secret,
            access_token=settings.x_access_token,
            access_token_secret=settings.x_access_secret,
            wait_on_rate_limit=True,
        )
        self.dry_run = dry_run

    def _check_daily_limit(self, already_published_today: int) -> bool:
        """Проверяет, не исчерпан ли дневной лимит."""
        if already_published_today >= settings.post_daily_limit:
            logger.warning(
                "Дневной лимит исчерпан: %d/%d постов",
                already_published_today,
                settings.post_daily_limit,
            )
            return False
        return True

    @retry(max_retries=3, exceptions=(tweepy.TweepyException, Exception))
    def publish(self, text: str) -> Optional[str]:
        """
        Публикует один твит.

        Args:
            text: Текст поста (уже обрезан до 280 символов).

        Returns:
            tweet_id опубликованного поста или None в dry-run / при ошибке.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Было бы опубликовано: %s", text[:100])
            return "dry_run_tweet_id"

        logger.info("Публикую пост через официальный API...")
        try:
            response = self.client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            logger.info("Успешно опубликовано! tweet_id=%s", tweet_id)
            return tweet_id
        except tweepy.TweepyException as exc:
            logger.error("Ошибка tweepy при публикации: %s", exc)
            raise
        except Exception as exc:
            logger.error("Неожиданная ошибка при публикации: %s", exc)
            raise

    def publish_batch(
        self,
        texts: list[str],
        already_published_today: int = 0,
    ) -> list[dict]:
        """
        Публикует пачку постов с соблюдением лимитов и задержек.

        Args:
            texts: Список черновиков.
            already_published_today: Сколько уже опубликовано сегодня.

        Returns:
            Список dict с tweet_id, content, cost_usd для каждого опубликованного.
        """
        results = []
        remaining_today = settings.post_daily_limit - already_published_today
        max_to_publish = min(len(texts), remaining_today, settings.post_per_run_limit)

        if max_to_publish <= 0:
            logger.info("Нет слота для публикации в этом цикле")
            return results

        logger.info(
            "Готовлюсь опубликовать %d пост(а) (уже сегодня: %d, лимит: %d)",
            max_to_publish,
            already_published_today,
            settings.post_daily_limit,
        )

        for idx, text in enumerate(texts[:max_to_publish], start=1):
            tweet_id = self.publish(text)
            if tweet_id:
                results.append({
                    "tweet_id": tweet_id,
                    "content": text,
                    "cost_usd": self.COST_PER_POST_USD,
                })

            # Задержка между постами, кроме последнего
            if idx < max_to_publish:
                delay = random.randint(settings.post_delay_min, settings.post_delay_max)
                logger.info("Пауза %d сек перед следующим постом...", delay)
                sync_delay(delay, delay)  # фиксированная задержка из диапазона

        return results
