# Combined image: builds the React frontend, then serves it from FastAPI.
# One container, one URL, no CORS. Used for single-service deploys (Render, etc.).

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # outputs /web/dist

# ---- Stage 2: backend + bundled frontend ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Bundle the built SPA; app.main serves it when backend/static exists.
COPY --from=frontend /web/dist ./static

EXPOSE 8000

# Bind to the platform-provided $PORT (Render/Railway) or 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
