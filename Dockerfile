# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

ARG MOTOR_REV=3
RUN echo "motor rev ${MOTOR_REV}" > /dev/null

COPY motor /app/motor
COPY backend /app/backend
COPY knowledge /app/knowledge

WORKDIR /app/backend
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
