"""
Веб-дашборд для X Hybrid Poster.
FastAPI + Jinja2 + SSE (логи в реальном времени).
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from main import Application
from utils import logger

app = FastAPI(title="X Hybrid Poster Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DRAFTS_DIR = Path("drafts")
LOGS_DIR = Path("logs")


def _get_app(dry_run: bool = False, fetch_all: bool = False) -> Application:
    """Фабрика Application (с инициализацией БД)."""
    from db import init_db
    init_db()
    return Application(dry_run=dry_run, fetch_all=fetch_all)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/generate")
async def api_generate():
    """Генерация черновиков (обычный режим)."""
    try:
        app_instance = _get_app(dry_run=True)
        draft_path = await app_instance.run_generate_only()
        return {"ok": True, "draft_file": str(draft_path)}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error("Ошибка генерации: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.post("/api/generate-force")
async def api_generate_force():
    """Форсированная генерация (игнорировать кэш)."""
    try:
        app_instance = _get_app(dry_run=True, fetch_all=True)
        draft_path = await app_instance.run_generate_only()
        return {"ok": True, "draft_file": str(draft_path)}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.error("Ошибка форсированной генерации: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.get("/api/draft")
async def api_get_draft():
    """Получить текущий черновик."""
    latest = DRAFTS_DIR / "latest.json"
    if not latest.exists():
        return {"ok": False, "error": "Черновик не найден. Сначала нажми 'Сгенерировать'"}
    data = json.loads(latest.read_text(encoding="utf-8"))
    return {"ok": True, "draft": data}


@app.post("/api/draft")
async def api_save_draft(request: Request):
    """Сохранить отредактированный черновик."""
    body = await request.json()
    posts = body.get("posts", [])
    if not posts:
        return {"ok": False, "error": "Пустой черновик"}

    latest = DRAFTS_DIR / "latest.json"
    if latest.exists():
        data = json.loads(latest.read_text(encoding="utf-8"))
    else:
        data = {"generated_at": datetime.utcnow().isoformat(), "model": "grok-3-mini"}

    data["posts"] = posts
    latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/publish-test")
async def api_publish_test():
    """Тестовая публикация (dry-run)."""
    try:
        app_instance = _get_app(dry_run=True)
        await app_instance.run_publish_draft(DRAFTS_DIR / "latest.json")
        return {"ok": True, "mode": "test"}
    except Exception as exc:
        logger.error("Ошибка тестовой публикации: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.post("/api/publish")
async def api_publish():
    """Живая публикация."""
    try:
        app_instance = _get_app(dry_run=False)
        await app_instance.run_publish_draft(DRAFTS_DIR / "latest.json")
        return {"ok": True, "mode": "live"}
    except Exception as exc:
        logger.error("Ошибка публикации: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.post("/api/clean-db")
async def api_clean_db():
    """Очистка базы данных."""
    try:
        from db import SessionLocal, cleanup_old_data
        with SessionLocal() as db:
            stats = cleanup_old_data(db)
        return {"ok": True, "stats": stats}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/logs/stream")
async def api_logs_stream():
    """SSE — поток логов в реальном времени."""
    log_file = _get_latest_log_file()
    if not log_file:
        return StreamingResponse(_empty_sse(), media_type="text/event-stream")

    return StreamingResponse(
        _tail_log_file(log_file),
        media_type="text/event-stream",
    )


def _get_latest_log_file() -> Path | None:
    if not LOGS_DIR.exists():
        return None
    files = sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


async def _empty_sse():
    yield "data: Логи не найдены\n\n"
    while True:
        await asyncio.sleep(5)
        yield "data: \n\n"


async def _tail_log_file(log_file: Path):
    """Читает файл лога с текущей позиции, шлёт новые строки через SSE."""
    if not log_file.exists():
        yield "data: Файл лога не найден\n\n"
        return

    position = log_file.stat().st_size
    yield f"data: Подключено к логам: {log_file.name}\n\n"

    while True:
        await asyncio.sleep(0.5)
        try:
            current_size = log_file.stat().st_size
            if current_size < position:
                # Файл был очищен — начинаем сначала
                position = 0
            if current_size > position:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(position)
                    new_lines = f.read()
                    position = f.tell()
                for line in new_lines.splitlines():
                    if line.strip():
                        yield f"data: {line}\n\n"
        except Exception:
            await asyncio.sleep(1)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=False)
