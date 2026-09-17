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

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements
COPY requirements.txt .

# Copy the Linux CPU-only PyTorch wheel downloaded on the host.
# This avoids downloading CUDA-enabled PyTorch and avoids
# the Docker certificate-chain problem with download.pytorch.org.
COPY torch-2.14.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl .

# Install CPU-only PyTorch
RUN pip install --no-cache-dir \
    ./torch-2.14.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl \
    && rm torch-2.14.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl

# Install remaining Python dependencies without reinstalling PyTorch
RUN sed '/^torch==/d' requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && rm requirements-docker.txt

# Copy application source
COPY . .

# Copy compiled React frontend
COPY --from=frontend-builder /app/frontend_dist ./frontend_dist

# Expose server port
EXPOSE 7860

# Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Start production server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]