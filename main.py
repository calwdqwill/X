"""
Точка входа в приложение.
Оркестрирует цикл: fetch → process → generate → post.
Поддерживает --dry-run для тестирования без публикации.
Поддерживает --generate-only для сохранения черновиков в файл.
Поддерживает --publish-draft для публикации отредактированных черновиков.
"""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from db import (
    SessionLocal,
    cleanup_old_data,
    count_published_today,
    get_latest_post_timestamp,
    get_recent_insights,
    get_unprocessed_posts,
    init_db,
    save_insights,
    save_posts,
    save_published_post,
)
from fetcher import TimelineFetcher
from generator import PostGenerator
from poster import XPoster
from processor import InsightProcessor
from scheduler import CycleScheduler
from utils import CostTracker, logger


DRAFTS_DIR = Path("drafts")


class Application:
    """Главный класс приложения, объединяющий все модули."""

    def __init__(self, dry_run: bool = False, fetch_all: bool = False) -> None:
        self.dry_run = dry_run
        self.fetch_all = fetch_all
        self.fetcher = TimelineFetcher()
        self.processor = InsightProcessor()
        self.generator = PostGenerator()
        self.poster = XPoster(dry_run=dry_run)
        self.scheduler = CycleScheduler()
        self.cost_tracker = CostTracker()
        self._shutdown = False

    async def run_generate_only(self) -> Path:
        """Выполняет fetch → process → generate и сохраняет черновики в JSON."""
        logger.info("=== Генерация черновиков ===")

        # --- CLEANUP ---
        with SessionLocal() as db:
            cleanup_old_data(db)

        # --- FETCH ---
        with SessionLocal() as db:
            since = get_latest_post_timestamp(db) if not self.fetch_all else None

        try:
            posts_data = await self.fetcher.fetch_timeline(count=100, since_timestamp=since)
        except Exception as exc:
            logger.error("Fetcher упал: %s", exc, exc_info=True)
            raise

        if not posts_data:
            logger.info("Новых постов нет")
            raise RuntimeError("Нет новых постов для генерации")

        with SessionLocal() as db:
            save_posts(db, posts_data)
            db.commit()

        # --- PROCESS ---
        with SessionLocal() as db:
            unprocessed = get_unprocessed_posts(db, limit=30)

        if unprocessed:
            try:
                insights_data = await self.processor.process_posts(unprocessed)
                with SessionLocal() as db:
                    save_insights(db, insights_data)
                    db.commit()
            except Exception as exc:
                logger.error("Processor упал: %s", exc)
                raise
        else:
            logger.info("Нет необработанных постов")
            raise RuntimeError("Нет постов для анализа")

        # --- GENERATE ---
        with SessionLocal() as db:
            recent_insights = get_recent_insights(db, hours=6, limit=15)

        if not recent_insights:
            logger.info("Нет свежих insights")
            raise RuntimeError("Нет insights для генерации")

        drafts = await self.generator.generate(insights=recent_insights, count=3)

        if not drafts:
            logger.info("Посты не сгенерировались")
            raise RuntimeError("Генерация вернула пустой результат")

        # --- SAVE DRAFT ---
        DRAFTS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        draft_file = DRAFTS_DIR / f"draft_{timestamp}.json"
        latest_file = DRAFTS_DIR / "latest.json"

        draft_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": settings.llm_model,
            "posts": drafts,
        }

        draft_file.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")
        latest_file.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Черновик сохранён: %s", draft_file)
        logger.info("Всего постов в черновике: %d", len(drafts))
        for i, text in enumerate(drafts, 1):
            print(f"\n--- Post {i} ---")
            print(text)
            print(f"Length: {len(text)} chars")
        print(f"\n✅ Черновик сохранён в: {draft_file}")
        print(f"   Также доступен как: {latest_file}")

        return draft_file

    async def run_publish_draft(self, draft_path: Path) -> None:
        """Читает черновик из файла и публикует посты через официальный API."""
        if not draft_path.exists():
            raise FileNotFoundError(f"Файл черновика не найден: {draft_path}")

        draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
        drafts = draft_data.get("posts", [])

        if not drafts:
            logger.info("В черновике нет постов")
            return

        logger.info("Публикация %d пост(а) из черновика: %s", len(drafts), draft_path)

        with SessionLocal() as db:
            published_today = count_published_today(db)

        try:
            results = self.poster.publish_batch(
                texts=drafts,
                already_published_today=published_today,
            )
            with SessionLocal() as db:
                for res in results:
                    save_published_post(
                        db,
                        content=res["content"],
                        tweet_id=res.get("tweet_id"),
                        cost_usd=res["cost_usd"],
                        is_dry_run=self.dry_run,
                    )
                    self.cost_tracker.add_post(1)
                db.commit()
        except Exception as exc:
            logger.error("Poster упал: %s", exc)
            raise

    async def run_once(self) -> None:
        """Выполняет один полный автоматический цикл."""
        logger.info("=== Начало цикла (dry_run=%s) ===", self.dry_run)

        try:
            draft_file = await self.run_generate_only()
        except RuntimeError:
            logger.info("Цикл завершён без генерации")
            return

        # В автоматическом режиме сразу публикуем
        await self.run_publish_draft(draft_file)
        logger.info("=== Конец цикла ===")

    async def run_scheduler(self) -> None:
        """Запускает цикл в бесконечном планировщике."""
        await self.run_once()
        self.scheduler.start(self.run_once)
        while not self._shutdown:
            await asyncio.sleep(1)

    def shutdown(self, signum, frame) -> None:
        logger.info("Получен сигнал %s, завершаю работу...", signum)
        self._shutdown = True
        self.scheduler.shutdown()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Гибридный X/Twitter бот: читает через twikit, публикует через API."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Режим сухого прогона: без реальной публикации",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Выполнить только один цикл и выйти (без планировщика)",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        default=False,
        help="Только сгенерировать черновик и сохранить в drafts/",
    )
    parser.add_argument(
        "--publish-draft",
        type=str,
        default=None,
        help="Путь к JSON-файлу черновика для публикации (например: drafts/latest.json)",
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        default=False,
        help="Игнорировать since_timestamp и взять все твиты из timeline (для тестирования)",
    )
    args = parser.parse_args()

    dry_run = args.dry_run or settings.dry_run
    if dry_run:
        logger.info("Активирован DRY-RUN режим")

    init_db()
    app = Application(dry_run=dry_run, fetch_all=args.fetch_all)

    signal.signal(signal.SIGINT, app.shutdown)
    signal.signal(signal.SIGTERM, app.shutdown)

    if args.generate_only:
        await app.run_generate_only()
    elif args.publish_draft:
        draft_path = Path(args.publish_draft)
        await app.run_publish_draft(draft_path)
    elif args.once:
        await app.run_once()
    else:
        await app.run_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
