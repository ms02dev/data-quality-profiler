# 1. Базовый образ. Slim-версия весит ~120 МБ (вместо 900 МБ у полной).
# OrbStack на M5 сам подтянет linux/arm64 версию.
FROM python:3.11-slim

# 2. Задаём рабочую директорию внутри контейнера
WORKDIR /app

# 3. Отключаем буферизацию stdout/stderr и создание .pyc файлов.
# В контейнерах логи должны появляться мгновенно, а кэш байт-кода не нужен.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 4. Копируем ТОЛЬКО зависимости и устанавливаем их.
# Это критически важно для кэширования слоёв Docker!
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Создаём non-root пользователя (best practice безопасности)
RUN addgroup --system appgroup && adduser --system --group appuser

# 6. Копируем исходный код приложения и тесты
COPY ./app ./app
COPY ./tests ./tests

# 7. Передаём права на папку новому пользователю
RUN chown -R appuser:appgroup /app

# 8. Переключаемся на non-root пользователя
USER appuser

# 9. Документируем порт (не пробрасывает его, просто подсказка для читающего)
EXPOSE 8000

# 10. Команда запуска. В продакшене reload=True НЕ НУЖЕН (он жрёт CPU и ломает graceful shutdown).
# Используем 1 worker для экономии ресурсов (для профайлера этого достаточно).
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]