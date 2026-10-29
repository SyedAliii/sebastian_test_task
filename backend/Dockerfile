FROM python:3.12-slim

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY alembic.ini .
COPY alembic alembic
