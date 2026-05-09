"""
Работа с базой данных: инициализация, сессии, CRUD-операции.
Все операции через SQLAlchemy 2.0 с typing support.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Generator, List, Optional

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from models import Base, Insight, Post, PublishedPost
from utils import logger

# ==========================================
# Инициализация движка и сессий
# ==========================================

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},  # необходимо для SQLite в многопотоке
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Создаёт все таблицы, если они ещё не существуют."""
    Base.metadata.create_all(bind=engine)
    logger.info("База данных инициализирована: %s", settings.db_path)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Контекстный менеджер для безопасной работы с сессией БД."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==========================================
# CRUD для Post
# ==========================================

def save_posts(db: Session, posts_data: List[dict]) -> int:
    """
    Массовое сохранение постов с дедупликацией по tweet_id.
    Возвращает количество вставленных записей.
    """
    if not posts_data:
        return 0

    # Получаем существующие tweet_id, чтобы не вставлять дубли
    tweet_ids = [p["tweet_id"] for p in posts_data]
    existing = db.execute(select(Post.tweet_id).where(Post.tweet_id.in_(tweet_ids))).scalars().all()
    existing_set = set(existing)

    new_posts = []
    for data in posts_data:
        if data["tweet_id"] in existing_set:
            continue
        new_posts.append(Post(**data))

    if new_posts:
        db.add_all(new_posts)
        db.flush()
        logger.info("Сохранено %d новых постов (пропущено дублей: %d)", len(new_posts), len(posts_data) - len(new_posts))
    else:
        logger.debug("Все %d постов уже есть в БД", len(posts_data))

    return len(new_posts)


def get_unprocessed_posts(db: Session, limit: int = 50) -> List[Post]:
    """Возвращает посты, у которых ещё нет insight."""
    stmt = (
        select(Post)
        .outerjoin(Insight)
        .where(Insight.id.is_(None))
        .order_by(Post.fetched_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def get_latest_post_timestamp(db: Session) -> Optional[datetime]:
    """Возвращает время создания самого свежего поста в БД (для since_timestamp логики)."""
    result = db.execute(select(func.max(Post.created_at))).scalar()
    return result


# ==========================================
# CRUD для Insight
# ==========================================

def save_insights(db: Session, insights: List[dict]) -> int:
    """Массовое сохранение insights. Каждый dict должен содержать post_id."""
    if not insights:
        return 0
    objects = [Insight(**i) for i in insights]
    db.add_all(objects)
    db.flush()
    logger.info("Сохранено %d insights", len(objects))
    return len(objects)


def get_recent_insights(db: Session, hours: int = 24, limit: int = 30) -> List[Insight]:
    """Возвращает insights за последние N часов, отсортированные по важности."""
    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(Insight)
        .where(Insight.processed_at >= since)
        .order_by(Insight.importance_score.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


# ==========================================
# CRUD для PublishedPost
# ==========================================

def save_published_post(
    db: Session,
    content: str,
    tweet_id: Optional[str] = None,
    cost_usd: float = 0.015,
    is_dry_run: bool = False,
) -> PublishedPost:
    """Сохраняет запись об опубликованном посте."""
    published = PublishedPost(
        tweet_id=tweet_id,
        content=content,
        cost_usd=cost_usd,
        is_dry_run=int(is_dry_run),
    )
    db.add(published)
    db.flush()
    logger.info("Сохранён лог публикации (dry_run=%s): id=%d", is_dry_run, published.id)
    return published


def count_published_today(db: Session) -> int:
    """Считает количество постов, опубликованных с начала текущих суток."""
    from utils import get_today_start
    today = get_today_start()
    stmt = select(func.count(PublishedPost.id)).where(PublishedPost.published_at >= today)
    return db.execute(stmt).scalar() or 0


def cleanup_old_data(db: Session, posts_hours: int = 24, insights_hours: int = 24, published_days: int = 30) -> dict:
    """Удаляет старые посты, insights и логи публикаций для очистки БД."""
    now = datetime.utcnow()
    stats = {}

    # Удаляем посты старше N часов
    post_cutoff = now - timedelta(hours=posts_hours)
    stmt = select(Post.id).where(Post.fetched_at < post_cutoff)
    old_post_ids = [row[0] for row in db.execute(stmt).all()]
    if old_post_ids:
        db.execute(select(Insight).where(Insight.post_id.in_(old_post_ids)))  # связанные insights
        db.query(Insight).filter(Insight.post_id.in_(old_post_ids)).delete(synchronize_session=False)
        db.query(Post).filter(Post.id.in_(old_post_ids)).delete(synchronize_session=False)
    stats["posts_deleted"] = len(old_post_ids)

    # Удаляем insights без постов (осиротевшие)
    orphan_insights = db.execute(
        select(Insight.id).outerjoin(Post).where(Post.id.is_(None))
    ).scalars().all()
    if orphan_insights:
        db.query(Insight).filter(Insight.id.in_(orphan_insights)).delete(synchronize_session=False)
    stats["orphan_insights_deleted"] = len(orphan_insights)

    # Удаляем логи публикаций старше N дней
    published_cutoff = now - timedelta(days=published_days)
    old_published = db.execute(
        select(PublishedPost.id).where(PublishedPost.published_at < published_cutoff)
    ).scalars().all()
    if old_published:
        db.query(PublishedPost).filter(PublishedPost.id.in_(old_published)).delete(synchronize_session=False)
    stats["published_logs_deleted"] = len(old_published)

    db.commit()
    logger.info("Очистка БД: posts=%d, orphan_insights=%d, published_logs=%d",
                stats["posts_deleted"], stats["orphan_insights_deleted"], stats["published_logs_deleted"])
    return stats
