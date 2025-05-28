FROM python:3.11

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "main.py"]

chown -R $(whoami) ~/.cache/pip
