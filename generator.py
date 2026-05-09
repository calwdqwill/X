"""
Генерация постов на основе свежих insights и vision.md.
Использует LLM для создания уникального контента в твоём стиле.
"""

import json
from pathlib import Path
from typing import List

from openai import AsyncOpenAI

from config import settings
from models import Insight
from utils import logger, retry, truncate_text


class PostGenerator:
    """Генератор постов: читает vision.md + insights, просит LLM написать твиты."""

    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.model = settings.llm_model
        self.vision_text = self._load_vision()

    def _load_vision(self) -> str:
        """Загружает vision.md или возвращает дефолтный prompt."""
        path = Path(settings.vision_path)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            logger.info("Vision загружен из %s (%d символов)", path, len(text))
            return text
        logger.warning("vision.md не найден по пути %s, использую дефолт", path)
        return (
            "Ты — опытный автор твитов. Пиши коротко, по делу, без воду. "
            "Максимум 280 символов."
        )

    def _build_prompt(self, insights: List[Insight], count: int = 2) -> str:
        """Собирает user-prompt для LLM из vision + insights."""
        lines = [
            "=== YOUR VISION AND STYLE ===",
            self.vision_text,
            "",
            "=== FRESH INSIGHTS FROM THE FEED ===",
        ]
        for ins in insights:
            lines.append(
                f"- [{ins.category}] {ins.summary} (importance: {ins.importance_score:.2f})"
            )
        lines.extend([
            "",
            f"=== TASK ===",
            f"Write {count} original posts for X/Twitter in the style described above.",
            "ACCOUNT FOCUS: Crypto trading, perpetual DEX (PerpDEX), DeFi, arbitrage, MEV, on-chain alpha. "
            "Prioritize insights about trading platforms, market inefficiencies, yield strategies, and airdrops. "
            "Only use AI/tech insights if they directly relate to trading automation or crypto tools.",
            "",
            "Each post must:\n"
            "1. Be unique (do not copy source posts verbatim).\n"
            "2. Contain your opinion, reaction, or addition to the insights.\n"
            "3. Fit within 280 characters.\n"
            "4. Be in English.\n"
            "\n"
            "Reply with a strictly valid JSON array of strings. Example: [\"Post 1...\", \"Post 2...\"]",
        ])
        return "\n".join(lines)

    @retry(max_retries=2, exceptions=(Exception,))
    async def generate(self, insights: List[Insight], count: int = 2) -> List[str]:
        """
        Генерирует 1–3 черновика постов на основе insights.

        Args:
            insights: Список свежих Insight.
            count: Сколько постов сгенерировать (1–3).

        Returns:
            Список строк (черновиков), готовых к публикации.
        """
        if not insights:
            logger.warning("Нет insights для генерации, пропускаю")
            return []

        count = max(1, min(count, 3))
        prompt = self._build_prompt(insights, count=count)
        logger.info("Запрашиваю генерацию %d постов у LLM...", count)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a professional X/Twitter copywriter."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.85,
            max_tokens=1500,
        )

        raw = response.choices[0].message.content or "[]"
        # Убираем markdown-обёртку если есть
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()

        try:
            drafts = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Генератор вернул невалидный JSON: %s\nRaw: %s", exc, raw)
            # Fallback: пытаемся взять текст как есть, разбив по переносам
            drafts = [line.strip("- \"'") for line in raw.split("\n") if line.strip() and len(line) > 20]

        if not isinstance(drafts, list):
            drafts = [str(drafts)]

        # Очистка и обрезка
        result = []
        for d in drafts:
            text = str(d).strip().strip('"').strip("'")
            text = truncate_text(text, 280)
            if text:
                result.append(text)

        logger.info("Сгенерировано %d постов", len(result))
        return result
