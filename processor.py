"""
Анализ постов через LLM: категоризация, summary, оценка важности.
Использует OpenAI-совместимый API (подходит для Grok, Anthropic-прокси, локальных моделей).
"""

import json
from typing import List

from openai import AsyncOpenAI

from config import settings
from models import Post
from utils import logger, retry


class InsightProcessor:
    """Процессор, который отправляет посты в LLM и получает структурированные insights."""

    SYSTEM_PROMPT = (
        "You are a content analyst for a crypto/trading-focused account. "
        "You receive a list of Twitter/X posts. "
        "For each post return a JSON object with fields:\n"
        "- category (str): topic of the post (Crypto, Trading, PerpDEX, DeFi, MEV, Arbitrage, Airdrop, AI, Other, etc.)\n"
        "- summary (str): brief 1–2 sentence summary in English\n"
        "- importance_score (float): score from 0.0 to 1.0, where 1.0 is the most useful/insightful post\n"
        "\n"
        "SCORING PRIORITY (highest to lowest):\n"
        "1. Perpetual DEX / PerpDEX platforms, trading mechanics, liquidity\n"
        "2. Crypto arbitrage, MEV, on-chain alpha, market inefficiencies\n"
        "3. DeFi protocols, yield strategies, airdrops\n"
        "4. Trading psychology, risk management, portfolio tools\n"
        "5. General crypto news, exploits, regulatory updates\n"
        "6. AI tools that directly help traders/automation\n"
        "7. Everything else (give low scores)\n"
        "\n"
        "Response must be a strictly valid JSON array of objects. "
        "The number of objects must exactly match the number of input posts."
    )

    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.model = settings.llm_model

    @retry(max_retries=3, exceptions=(Exception,))
    async def process_posts(self, posts: List[Post]) -> List[dict]:
        """
        Отправляет список постов в LLM и возвращает список insights.

        Args:
            posts: Список ORM-объектов Post.

        Returns:
            Список dict с ключами post_id, category, summary, importance_score.
        """
        if not posts:
            return []

        # Формируем user-content: нумерованный список постов
        user_lines = []
        for idx, post in enumerate(posts, start=1):
            text = post.content.replace("\n", " ")[:500]  # обрезаем очень длинные
            user_lines.append(f"{idx}. [@{post.author_username}]: {text}")

        user_content = "\n".join(user_lines)
        logger.info("Отправляю %d постов в LLM для анализа...", len(posts))

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content or "[]"
        # Иногда модель оборачивает ответ в ```json ... ```
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM вернул невалидный JSON: %s\nRaw: %s", exc, raw)
            raise

        if not isinstance(parsed, list):
            logger.error("LLM вернул не массив: %s", type(parsed))
            raise ValueError("Ожидался JSON-массив insights")

        if len(parsed) != len(posts):
            logger.warning(
                "LLM вернул %d insights при %d постах. Пробуем сопоставить по порядку.",
                len(parsed),
                len(posts),
            )

        insights = []
        for post, item in zip(posts, parsed):
            insights.append({
                "post_id": post.id,
                "category": str(item.get("category", "Other")),
                "summary": str(item.get("summary", "")),
                "importance_score": float(item.get("importance_score", 0.0)),
            })

        logger.info("Получено %d insights от LLM", len(insights))
        return insights
