# Multi-stage Production Dockerfile for ChangeGuard
# ---------------------------------------------------

# Stage 1: Build the React frontend with Vite
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


# Stage 2: Production Python API backend & static file serving
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files to disk and buffer stdout
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies.
# libgomp1 is the OpenMP runtime LightGBM needs on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Copy compiled React frontend
COPY --from=frontend-builder /app/frontend_dist ./frontend_dist

# Expose server port
EXPOSE 7860

# Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/health || exit 1

# Start production server.
# A single worker on purpose: each worker independently loads both risk
# models and their FAISS indexes, and one worker comfortably fits the
# 512MB RAM of small/free hosting tiers.
#
# $PORT is set by hosts such as Render; 7860 is the local default.
# --proxy-headers makes the real client IP (X-Forwarded-For) visible,
# so the login rate limit is per user rather than per load balancer.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]