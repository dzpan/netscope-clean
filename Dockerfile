# Stage 1: Python dependencies — compile C extensions, then discard build tools
FROM python:3.11.9-slim-bookworm AS python-deps
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Install into an isolated prefix so we can copy just the packages
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Frontend build
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 3: Minimal runtime image — no build tools
FROM python:3.11.9-slim-bookworm AS runtime

LABEL maintainer="PaperclipAI <noreply@paperclip.ing>"
LABEL org.opencontainers.image.title="NetScope"
LABEL org.opencontainers.image.description="SSH-based network topology intelligence for Cisco networks"
LABEL org.opencontainers.image.version="1.1.0"
LABEL org.opencontainers.image.source="https://github.com/paperclipai/netscope"

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app app \
    && mkdir -p /data && chown app:app /data

# Copy compiled Python packages
COPY --from=python-deps /install /usr/local

# Copy application source and built frontend
COPY backend/ backend/
COPY --from=frontend-build /frontend/dist frontend/dist

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NETSCOPE_STATIC_DIR=frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

USER app

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
