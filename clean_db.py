"""Скрипт для полной очистки базы данных. Запускать перед 'свежим стартом'."""
from db import SessionLocal, init_db
from models import Post, Insight, PublishedPost
from utils import logger

def clean_all():
    init_db()
    with SessionLocal() as db:
        logger.info("Удаляю все данные из БД...")
        db.query(PublishedPost).delete(synchronize_session=False)
        db.query(Insight).delete(synchronize_session=False)
        db.query(Post).delete(synchronize_session=False)
        db.commit()
        logger.info("База очищена.")

if __name__ == "__main__":
    clean_all()
