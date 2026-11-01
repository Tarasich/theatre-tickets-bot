FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY theatre_bot ./theatre_bot
# Состояние и лог храним в томе /app/data, чтобы они переживали пересоздание контейнера
ENV STATE_FILE=data/state.json LOG_FILE=data/bot.log PYTHONUNBUFFERED=1
RUN mkdir -p data
CMD ["python", "-m", "theatre_bot"]
