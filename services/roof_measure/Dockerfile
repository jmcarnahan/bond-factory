# roof_measure service image. Build context is the REPO ROOT (uv workspace lock, ../../fixtures):
#   docker buildx build --platform linux/amd64 -f services/roof_measure/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg \
    UV_COMPILE_BYTECODE=0 UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH \
    DATA_DIR=/data ROOF_MEASURE_CACHE=/data/cache ROOF_MEASURE_FIXTURES=/app/fixtures

# libgomp1: kept as a precaution; the compas_cgal 0.10.0 wheel links no OpenMP (checked 2026-11-11).
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.13.7

WORKDIR /app
# dependencies first (cached until the lock or a pyproject changes)
COPY pyproject.toml uv.lock ./
COPY services/roof_measure/pyproject.toml services/roof_measure/pyproject.toml
RUN uv sync --frozen --package roof-measure --no-dev --no-install-project --extra service --extra render

COPY services/roof_measure/ services/roof_measure/
COPY fixtures/ fixtures/
RUN uv sync --frozen --package roof-measure --no-dev --no-editable --extra service --extra render

RUN useradd --create-home --uid 10001 app && mkdir -p /data/cache && chown -R app:app /data
USER app
EXPOSE 8011

# Binds :: by default, which uvicorn opens IPv6-only (right for Railway; local Docker needs ROOF_MEASURE_HOST=0.0.0.0).
# ROOF_MEASURE_TOKEN is required at start-up; the /data volume is attached in Railway's UI (no VOLUME instruction).
CMD ["sh", "-c", "exec uvicorn roof_measure.api:app --host ${ROOF_MEASURE_HOST:-::} --port ${PORT:-8011}"]
