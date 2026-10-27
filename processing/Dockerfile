FROM python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5 AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 RUFF_CACHE_DIR=/tmp/ruff-cache
WORKDIR /app
COPY processing/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock
COPY processing/device_health_ingestion /app/device_health_ingestion
USER 10001:10001
ENTRYPOINT ["python", "-m", "device_health_ingestion"]

FROM runtime AS test
USER root
COPY processing/requirements-dev.lock /app/requirements-dev.lock
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-dev.lock
COPY processing/tests /app/tests
COPY processing/pyproject.toml /app/pyproject.toml
COPY processing/demo.py /app/demo.py
USER 10001:10001
ENTRYPOINT []
CMD ["python", "-m", "pytest", "-m", "not integration", "-q", "-o", "cache_dir=/tmp/pytest-cache"]
