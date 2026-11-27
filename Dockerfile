FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system appuser && useradd --system --gid appuser --home-dir /app appuser

COPY --chown=appuser:appuser pyproject.toml ./
COPY --chown=appuser:appuser app ./app
RUN pip install --no-cache-dir ".[dev]" && rm -rf /app/*.egg-info /app/build

COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser tests ./tests

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
