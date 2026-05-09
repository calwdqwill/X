# X Hybrid Poster

**Автоматический бот для X/Twitter** с гибридным подходом: читает ленту Following через неофициальное API ([twikit](https://github.com/d60/twikit)), анализирует через LLM ([xAI Grok](https://x.ai/api)), генерирует уникальные посты в твоём стиле и публикует через официальное X API v2.

---

## ⚡ Возможности

- **Smart Feed Reading** — парсит хронологическую ленту Following, фильтрует ретвиты и ответы
- **AI Analysis** — Grok оценивает каждый твит по важности и категории (Crypto, Trading, PerpDEX, DeFi)
- **Style Generation** — создаёт посты на основе `vision.md` (твоего стиля и тона)
- **Safe Publishing** — публикует через официальный X API с задержками и лимитами
- **Manual Approval** — все черновики сохраняются в файл, ты правишь перед публикацией
- **Auto Cleanup** — база данных автоматически очищается от старых записей

---

## 📁 Структура (25 файлов)

| Файл | Описание |
|------|----------|
| `main.py` | Точка входа. Оркестрирует цикл: fetch → process → generate → post |
| `fetcher.py` | Чтение ленты Following через twikit (cookies) с monkey-patches |
| `processor.py` | Отправляет твиты в Grok для анализа (category, summary, importance_score) |
| `generator.py` | Генерирует 3 готовых поста на основе топ-insights + vision.md |
| `poster.py` | Публикация через tweepy (X API v2) с дневными/запусковыми лимитами |
| `scheduler.py` | APScheduler для периодического запуска (20-30 мин интервал) |
| `db.py` | SQLite ORM (SQLAlchemy): Post, Insight, PublishedPost + cleanup |
| `models.py` | SQLAlchemy модели |
| `config.py` | Pydantic Settings, читает `.env` |
| `utils.py` | Логирование, retry-декоратор, задержки, трекинг стоимости |
| `vision.md` | Твой style guide (tone, focus, constraints) для LLM |
| `.env.example` | Шаблон переменных окружения |
| `.gitignore` | Исключает secrets, БД, логи |
| `requirements.txt` | Зависимости |
| `Dockerfile` | Контейнеризация |
| `clean_db.py` + `clean_db.bat` | Полная очистка базы данных |
| `run_generate.bat` | Генерация черновиков (2 клика) |
| `run_generate_force.bat` | Форсированная генерация (игнорирует кэш) |
| `run_publish.bat` | Живая публикация (с подтверждением) |
| `run_publish_test.bat` | Тестовая публикация (dry-run, без реальных твитов) |
| `setup_scheduler.ps1` | Создаёт задачу Windows Task Scheduler (9:00 утра) |
| `remove_scheduler.ps1` | Удаляет задачу из Task Scheduler |

---

## 🚀 Быстрый старт

### 1. Установка
```bash
git clone <repo>
cd x_hybrid_poster
pip install -r requirements.txt
```

### 2. Настройка
```bash
cp .env.example .env
# Отредактируй .env — вставь свои ключи
```

Обязательные переменные:
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` — X Developer Portal
- `LLM_API_KEY` — [xAI Console](https://console.x.ai)
- `cookies.json` — экспортируй cookies из браузера (x.com) через Cookie-Editor

### 3. Генерация черновиков
```bash
python main.py --generate-only --dry-run
```
Или просто двойной клик: **`run_generate.bat`**

Результат: `drafts/latest.json` с 3 постами.

### 4. Правка
Открой `drafts/latest.json`, отредактируй тексты.

### 5. Публикация
```bash
# Тест (ничего не постит)
python main.py --publish-draft drafts/latest.json --dry-run

# Живая публикация
python main.py --publish-draft drafts/latest.json
```
Или двойной клик: **`run_publish.bat`**

---

## 💰 Стоимость

| Действие | Цена |
|----------|------|
| Генерация 3 постов | ~$0.03 (2 запроса к Grok) |
| Публикация 3 постов | ~$0.003 (X API Pay-Per-Use) |

---

## ⚙️ Аргументы командной строки

```bash
python main.py --generate-only          # Только сгенерировать черновик
python main.py --publish-draft PATH     # Опубликовать из JSON-файла
python main.py --dry-run                # Режим сухого прогона
python main.py --once                   # Один цикл и выйти
python main.py --fetch-all              # Игнорировать кэш, взять все твиты
```

---

## 🔒 Безопасность

- `.env` и `cookies.json` — **никогда не коммить** (уже в `.gitignore`)
- `run_publish.bat` требует ввода `yes` перед живой публикацией
- `run_publish_test.bat` — безопасный тест без реальных постов

---

## 📝 Кастомизация

Отредактируй `vision.md` — это твой style guide для LLM:
- Tone: Bold, builder-first
- Focus: Crypto trading, PerpDEX, DeFi
- Constraints: Max 280 chars, English only

---

## 📜 Ветка

Проект в ветке: **`twitter_auto`**
