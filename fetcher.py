"""
Модуль чтения ленты Following через twikit.
Работает через cookies (браузерный логин), т.к. автологин twikit сейчас сломан.
Все read-операции с human-like задержками для снижения риска бана.
"""

import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
from twikit import Client as TwikitClient
from twikit.x_client_transaction import transaction
import twikit.tweet as _tweet_module
import twikit.client.client as _client_module
import twikit.user as _user_module

from config import settings
from utils import async_delay, logger, retry

# ==========================================
# FIX 1: Twikit сейчас сломан для автологина (X изменил HTML).
# Обходим client_transaction.init, чтобы не падал на отсутствии ondemand.s
# ==========================================

_original_init = transaction.ClientTransaction.init

async def _patched_init(self, session, headers):
    """No-op init: пропускаем сложную инициализацию, хардкодим минимум."""
    self.home_page_response = True
    # Генерируем валидный base64 key (32 байта → 44 символа base64)
    import base64 as _b64
    self.key = _b64.b64encode(b'X' * 32).decode()
    self.key_bytes = self.get_key_bytes(self.key)
    self.DEFAULT_ROW_INDEX = 2
    self.DEFAULT_KEY_BYTES_INDICES = [12, 14, 7]
    try:
        self.animation_key = self.get_animation_key(self.key_bytes, None)
    except Exception:
        self.animation_key = "0" * 32

transaction.ClientTransaction.init = _patched_init

# Также подменяем generate_transaction_id на более стабильный
_original_generate = transaction.ClientTransaction.generate_transaction_id

def _patched_generate(self, method: str, path: str, **kwargs):
    """Генерируем фейковый, но валидно выглядящий transaction_id."""
    import base64
    import hashlib
    import math
    import random
    import time

    time_now = math.floor((time.time() * 1000 - 1682924400 * 1000) / 1000)
    time_now_bytes = [(time_now >> (i * 8)) & 0xFF for i in range(4)]
    key_bytes = self.key_bytes or [0] * 32
    random_num = random.randint(0, 255)
    hash_val = hashlib.sha256(f"{method}!{path}!{time_now}bird".encode()).digest()
    hash_bytes = list(hash_val)
    bytes_arr = [*key_bytes, *time_now_bytes, *hash_bytes[:16], 3]
    out = bytearray([random_num, *[item ^ random_num for item in bytes_arr]])
    return base64.b64encode(out).decode().strip("=")

transaction.ClientTransaction.generate_transaction_id = _patched_generate

# ==========================================
# FIX 3: Некоторые пользователи приходят с неполными legacy-полями.
# Заменяем User.__init__ на версию с .get() вместо прямых обращений.
# ==========================================

_original_user_init = _user_module.User.__init__

def _patched_user_init(self, client, data):
    self._client = client
    self._data = data
    legacy = data.get('legacy', {})

    self.id = data.get('rest_id', '0')
    self.created_at = legacy.get('created_at', '')
    self.name = legacy.get('name', 'unknown')
    self.screen_name = legacy.get('screen_name', 'unknown')
    self.profile_image_url = legacy.get('profile_image_url_https', '')
    self.profile_banner_url = legacy.get('profile_banner_url')
    self.url = legacy.get('url')
    self.location = legacy.get('location', '')
    self.description = legacy.get('description', '')
    self.description_urls = legacy.get('entities', {}).get('description', {}).get('urls', [])
    self.urls = legacy.get('entities', {}).get('url', {}).get('urls')
    self.pinned_tweet_ids = legacy.get('pinned_tweet_ids_str', [])
    self.is_blue_verified = data.get('is_blue_verified', False)
    self.verified = legacy.get('verified', False)
    self.possibly_sensitive = legacy.get('possibly_sensitive', False)
    self.can_dm = legacy.get('can_dm', False)
    self.can_media_tag = legacy.get('can_media_tag', False)
    self.want_retweets = legacy.get('want_retweets', False)
    self.default_profile = legacy.get('default_profile', False)
    self.default_profile_image = legacy.get('default_profile_image', False)
    self.has_custom_timelines = legacy.get('has_custom_timelines', False)
    self.followers_count = legacy.get('followers_count', 0)
    self.fast_followers_count = legacy.get('fast_followers_count', 0)
    self.normal_followers_count = legacy.get('normal_followers_count', 0)
    self.following_count = legacy.get('friends_count', 0)
    self.favourites_count = legacy.get('favourites_count', 0)
    self.listed_count = legacy.get('listed_count', 0)
    self.media_count = legacy.get('media_count', 0)
    self.statuses_count = legacy.get('statuses_count', 0)
    self.is_translator = legacy.get('is_translator', False)
    self.translator_type = legacy.get('translator_type', '')
    self.withheld_in_countries = legacy.get('withheld_in_countries', [])
    self.protected = legacy.get('protected', False)

_user_module.User.__init__ = _patched_user_init

# Дополнительная защита: если tweet_from_data всё равно падает — пропускаем твит
_original_tweet_from_data = _tweet_module.tweet_from_data

def _safe_tweet_from_data(client, data):
    try:
        return _original_tweet_from_data(client, data)
    except KeyError as exc:
        logger.debug("tweet_from_data пропустил твит из-за KeyError: %s", exc)
        return None
    except Exception as exc:
        logger.debug("tweet_from_data пропустил твит из-за %s: %s", type(exc).__name__, exc)
        return None

_tweet_module.tweet_from_data = _safe_tweet_from_data
_client_module.tweet_from_data = _safe_tweet_from_data


class TimelineFetcher:
    """Обертка над twikit для безопасного чтения ленты Following."""

    def __init__(self, cookies_path: Optional[str] = None) -> None:
        self.cookies_path = Path(cookies_path or settings.twikit_cookies_path)
        self.client = TwikitClient("en-US", timeout=30.0)
        self._logged_in = False

        # FIX: заменяем twikit's http на свежий httpx клиент (обход ConnectTimeout)
        self.client.http = httpx.AsyncClient(
            proxy=settings.http_proxy,
            timeout=30.0,
            follow_redirects=True,
        )

        # Если задан прокси, пробрасываем в httpx через env-переменные
        if settings.http_proxy:
            os.environ["HTTP_PROXY"] = settings.http_proxy
            os.environ["HTTPS_PROXY"] = settings.http_proxy
            logger.info("Используется прокси: %s", settings.http_proxy)

    async def ensure_login(self) -> None:
        """
        Авторизуется в X через twikit используя cookies.
        Если cookies не найдены — кидает ошибку с инструкцией.
        """
        if self._logged_in:
            return

        if self.cookies_path.exists():
            logger.info("Загружаю cookies из %s", self.cookies_path)
            try:
                self.client.load_cookies(str(self.cookies_path))
                self._logged_in = True
                logger.info("Авторизация через cookies прошла успешно")
                return
            except Exception as exc:
                logger.error("Не удалось загрузить cookies: %s", exc)
                raise RuntimeError(
                    "Cookies повреждены или устарели. "
                    "Экспортируй свежие cookies из браузера (auth_token + ct0) и сохрани в cookies.json"
                ) from exc

        raise RuntimeError(
            "Cookies не найдены. Автологин twikit сейчас сломан (X изменил фронтенд).\n"
            "Инструкция:\n"
            "1. Залогинься в x.com через Chrome/Edge с VPN\n"
            "2. Установи расширение Cookie-Editor\n"
            "3. Экспортируй cookies для x.com в JSON\n"
            f"4. Сохрани файл по пути: {self.cookies_path.absolute()}\n"
            "Главные поля: auth_token, ct0, guest_id, twid"
        )

    @retry(max_retries=3, exceptions=(Exception,))
    async def fetch_timeline(
        self,
        count: int = 50,
        since_timestamp: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Получает ленту Following через get_timeline().

        Args:
            count: Количество твитов для загрузки (40–60 оптимально).
            since_timestamp: Если указан, фильтрует посты старше этой даты.

        Returns:
            Список словарей с нормализованными данными постов.
        """
        await self.ensure_login()

        # Задержка перед запросом (human-like)
        await async_delay(settings.fetch_delay_min, settings.fetch_delay_max)

        logger.info("Запрашиваю timeline (count=%d)...", count)
        try:
            tweets = await self.client.get_latest_timeline(count=count)
            logger.info("Twikit (latest) вернул %d твитов (до фильтрации)", len(tweets))
        except AttributeError:
            tweets = await self.client.get_timeline(count=count)
            logger.info("Twikit (home) вернул %d твитов (до фильтрации)", len(tweets))

        posts: List[dict] = []
        skipped_rt = skipped_reply = skipped_old = skipped_error = 0
        for tweet in tweets:
            if tweet is None:
                skipped_error += 1
                continue
            # Пропускаем ретвиты и ответы по желанию
            if tweet.retweeted_tweet:
                skipped_rt += 1
                continue
            if tweet.in_reply_to:
                skipped_reply += 1
                continue

            created_at: Optional[datetime] = None
            try:
                created_at = getattr(tweet, "created_at_datetime", None)
                if created_at is None and hasattr(tweet, "created_at"):
                    created_at = datetime.strptime(tweet.created_at, "%a %b %d %H:%M:%S %z %Y")
            except Exception as exc:
                logger.debug("Не удалось распарсить дату твита: %s", exc)
                created_at = datetime.utcnow()

            # Фильтрация по since_timestamp (опциональная — если нужен строгий режим)
            # NOTE: отключена по умолчанию, т.к. save_posts сама дедуплицирует по tweet_id,
            # а ограниченное окно timeline часто возвращает уже известные твиты.
            # if since_timestamp and created_at:
            #     created_at_naive = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
            #     if created_at_naive < since_timestamp:
            #         skipped_old += 1
            #         continue

            post_data = {
                "tweet_id": str(tweet.id),
                "author_username": str(getattr(tweet.user, "screen_name", getattr(tweet.user, "name", "unknown"))),
                "author_name": str(getattr(tweet.user, "name", "")),
                "content": str(tweet.text),
                "created_at": created_at,
                "raw_json": json.dumps({
                    "id": str(tweet.id),
                    "text": str(tweet.text),
                    "created_at": str(getattr(tweet, "created_at", "")),
                    "user": {
                        "screen_name": getattr(tweet.user, "screen_name", ""),
                        "name": getattr(tweet.user, "name", ""),
                    },
                }, ensure_ascii=False),
            }
            posts.append(post_data)

            # Небольшая задержка между итерациями обработки (имитируем чтение)
            await asyncio.sleep(random.uniform(0.3, 1.2))

        logger.info(
            "Получено %d постов | пропущено: рт=%d, ответ=%d, старые=%d, ошибки=%d",
            len(posts), skipped_rt, skipped_reply, skipped_old, skipped_error,
        )
        return posts
