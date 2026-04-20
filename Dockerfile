# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed for some packages (pandas, Pillow, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir gunicorn==22.0.0 -r requirements.txt


# ── Stage 2: production image ─────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Remove dev/secrets files — never bake them into the image
RUN rm -f .env rts_inventory.db

# Create volume mount point for persistent data
RUN mkdir -p /data && \
    # Static uploads (logos, etc.)
    mkdir -p /app/static/images

# Non-root user for security
RUN useradd -m -u 1000 rts && chown -R rts:rts /app /data
USER rts

# Gunicorn on port 8000 (nginx or a load-balancer sits in front)
EXPOSE 8000

# DATABASE_URL and SECRET_KEY MUST be injected at runtime via env vars or secrets
ENV DATABASE_URL=sqlite:////data/rts_inventory.db \
    FLASK_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
