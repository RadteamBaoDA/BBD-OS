FROM python:3.12.14-slim-bookworm AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.12.11 && uv sync --frozen --no-dev
COPY apps ./apps
COPY core ./core
COPY modules ./modules
COPY infrastructure/postgres/migrations ./infrastructure/postgres/migrations
COPY alembic.ini ./alembic.ini

FROM python:3.12.14-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --system --gid 10001 bbd && useradd --system --uid 10001 --gid bbd --no-create-home bbd
COPY --from=build --chown=bbd:bbd /app /app
USER bbd
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
