# Stage 1: Build React Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Run Python FastAPI Backend
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application backend code
COPY . .

# Copy built frontend static files from Stage 1 into frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose default port
EXPOSE 8000

# Start command
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
