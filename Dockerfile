# ==========================================
# Гибридный X/Twitter бот
# Читает через twikit, публикует через официальный API
# ==========================================

FROM python:3.12-slim

# Устанавливаем зависимости системы (если нужны компиляторы для некоторых пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости отдельно для кэширования слоя
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Том для SQLite БД и cookies (чтобы не терять при пересоздании контейнера)
VOLUME ["/app/data"]

# Переменная окружения для пути к БД внутри контейнера
ENV DB_PATH=/app/data/x_hybrid.db
ENV TWIKIT_COOKIES_PATH=/app/data/cookies.json
ENV PYTHONUNBUFFERED=1

# Запускаем в режиме планировщика
CMD ["python", "main.py"]
