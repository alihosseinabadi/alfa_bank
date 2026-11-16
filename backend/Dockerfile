# Alfa-Kurs API image: FastAPI + migrations + reward worker.
# Installs exact versions from requirements.lock.txt; no private data or secrets.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY backend/requirements.txt backend/requirements-catalog.txt backend/requirements.lock.txt /app/backend/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/backend/requirements.lock.txt

COPY backend /app/backend
COPY scripts /app/scripts

# Mount point for the synthetic demo catalogue built at container start; the
# directory must exist before the named volume is attached so it inherits the
# unprivileged owner instead of root:root.
RUN mkdir -p /app/demo-bundles && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
