# syntax=docker/dockerfile:1

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# System dependencies required at install time
# --mount=type=cache 让 apt 缓存跨构建复用，避免重复下载
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    git

WORKDIR /app

# Install Python dependencies
# --mount=type=cache 让 pip 缓存跨构建复用：requirements.txt 局部变更时只下载新增包
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# Pre-download NLTK corpora so the container starts without needing internet
COPY scripts/download_nltk_data.py scripts/download_nltk_data.py
RUN python scripts/download_nltk_data.py

# Pre-download sentence-transformers embedding models（避免运行时联网下载）
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-mpnet-base-v2'); \
SentenceTransformer('all-MiniLM-L6-v2')"


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Minimal runtime system libraries（保留 curl 供健康检查使用）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy NLTK data and model cache downloaded in builder stage
COPY --from=builder /root/nltk_data /root/nltk_data
COPY --from=builder /root/.cache /root/.cache

# Copy application source code
COPY src/ src/
COPY scripts/ scripts/
COPY data/ data/

# Environment variables (override at runtime via -e or --env-file)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GEMINI_API_KEY="" \
    GEMINI_MODEL="gemini-2.0-flash" \
    MOONSHOT_API_KEY="" \
    MOONSHOT_MODEL="kimi-k2-turbo-preview"

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 生产启动：host 0.0.0.0 才能被容器外访问，不开 --reload
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
