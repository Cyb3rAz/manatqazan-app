# ── ManatAds Dockerfile ──────────────────────────────────────────────
# Multi-stage build: slim Python 3.11 image
FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ── Dependencies ──
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Application code ──
COPY . .

# ── Expose port ──
EXPOSE 8000

# ── Health check ──
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── Run ──
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
