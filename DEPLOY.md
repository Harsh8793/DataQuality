# Deploying DataPilot AI (free)

The app ships as **one container**: the React frontend is built and served by the
FastAPI backend, so there's a single URL and no CORS setup. This is the simplest
way to get a free live demo.

## Option A — Render (recommended, free)

1. Push this repo to GitHub.
2. Go to **render.com → New → Blueprint** and select this repository.
   Render reads [`render.yaml`](./render.yaml) and creates one web service.
3. When prompted, set the **`GROQ_API_KEY`** environment variable (your Groq key).
   `JWT_SECRET` is generated automatically.
4. Deploy. Render builds [`Dockerfile`](./Dockerfile) (frontend + backend) and gives
   you a URL like `https://datapilot-ai.onrender.com` — that's the whole app.

**Health check:** `GET /health` should return `{"status":"healthy"}`.

## Option B — any Docker host (Railway, Fly.io, Hugging Face Spaces…)

The root `Dockerfile` is self-contained:

```bash
docker build -t datapilot .
docker run -p 8000:8000 -e GROQ_API_KEY=sk_... -e JWT_SECRET=$(openssl rand -hex 32) datapilot
# open http://localhost:8000
```

Point the platform at the repo root `Dockerfile`, set `GROQ_API_KEY` + `JWT_SECRET`,
and expose the `$PORT` it provides (the container already binds to `$PORT`).

## ⚠️ Data persistence

Free tiers use an **ephemeral disk**. The SQLite DB, uploaded files, and Parquet
caches live under `/app/data` and **reset on every redeploy and when a free service
sleeps/restarts**. This is fine for a demo — just re-upload a dataset when you present.

To keep data across restarts, attach a persistent disk mounted at **`/app/data`**
(Render Disk, Fly volume, etc.), or move the DB to managed Postgres by setting
`DATABASE_URL` (files would still need a mounted disk or object storage).

## Environment variables

| Variable        | Required | Notes                                             |
|-----------------|----------|---------------------------------------------------|
| `GROQ_API_KEY`  | yes      | Groq key; AI features fall back gracefully if unset |
| `JWT_SECRET`    | yes      | Any long random string (Render auto-generates)    |
| `GROQ_MODEL`    | no       | Defaults to `llama-3.1-8b-instant`                |
| `APP_ENV`       | no       | `production` in deploys                           |
| `CORS_ORIGINS`  | no       | Not needed for the single-container deploy        |
| `DATABASE_URL`  | no       | Override to use Postgres instead of SQLite        |

## Local development (unchanged)

Two processes as before — Vite proxies `/api` to the backend, so the bundled
static serving stays off:

```bash
# backend
cd backend && uvicorn app.main:app --reload
# frontend
cd frontend && npm run dev   # http://localhost:5173
```
