"""
SQLAlchemy ORM модели для хранения постов, insights и опубликованного контента.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, Integer, String, Text, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


class Post(Base):
    """Сырой пост из ленты Following, полученный через twikit."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    author_username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Связь: один пост может иметь один insight
    insight: Mapped[Optional["Insight"]] = relationship("Insight", back_populates="post", uselist=False)

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, tweet_id={self.tweet_id}, author={self.author_username})>"


class Insight(Base):
    """Результат анализа поста LLM: категория, summary, важность."""

    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False, unique=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Обратная связь
    post: Mapped["Post"] = relationship("Post", back_populates="insight")

    def __repr__(self) -> str:
        return f"<Insight(id={self.id}, post_id={self.post_id}, score={self.importance_score})>"


class PublishedPost(Base):
    """Лог опубликованных постов через официальный API."""

    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.015)
    is_dry_run: Mapped[bool] = mapped_column(Integer, default=0)  # 0/1 для SQLite

    def __repr__(self) -> str:
        return f"<PublishedPost(id={self.id}, tweet_id={self.tweet_id}, dry_run={self.is_dry_run})>"
