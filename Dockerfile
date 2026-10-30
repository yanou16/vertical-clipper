# --- 1) build the React app ---------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2) runtime: FastAPI + FFmpeg ---------------------------------------------
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --default-timeout=120 --retries=5 -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist

RUN useradd --create-home clipper && mkdir -p /app/data && chown clipper /app/data
USER clipper
ENV CLIPPER_DATA_DIR=/app/data
EXPOSE 8000
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
