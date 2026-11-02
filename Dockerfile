FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY web ./web
COPY scripts ./scripts

# SQLite lives on a volume so data survives container restarts.
ENV DATABASE_URL=sqlite:////data/sapfico.db
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Seed is idempotent (merge by primary key), so it is safe on every start.
CMD ["sh", "-c", "python -m app.seed && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
