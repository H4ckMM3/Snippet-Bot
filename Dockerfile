FROM python:3.11

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt отдельно для кэширования слоя
COPY requirements.txt .

# Обновляем pip и устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip check

# Копируем остальные файлы
COPY main.py .

# Устанавливаем переменную окружения для вывода логов в реальном времени
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "snippet_bot.py"]

RUN mkdir -p /app/data && chmod -R 777 /app/data