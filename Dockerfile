# ChangeGuard production container
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (this layer is cached for faster rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole project
COPY . .

# Build the ML model and FAISS index at image-build time
RUN python src/train_model.py && python src/build_index.py

# Port for the web server
EXPOSE 7860

# Production server (no --reload)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
