# Multi-stage build: compile the Vite SPA with Node, then run FastAPI (which
# serves the built static files + /api) on Python. One image, one service.

# --- Stage 1: build the frontend ---------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /build/frontend

# The client bundle needs the Discord client id at *build* time (Vite inlines
# VITE_* vars). The deploy passes it as a build arg (see scripts/lightsail_deploy.sh).
ARG VITE_DISCORD_CLIENT_ID
ENV VITE_DISCORD_CLIENT_ID=$VITE_DISCORD_CLIENT_ID

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime -------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY backend/ ./

ENV PATH="/app/.venv/bin:$PATH"

# Bring the built SPA in where the backend expects it (ACTIVITY_STATIC_DIR
# default is ../static relative to app/, i.e. /app/static).
COPY --from=frontend /build/frontend/dist ./static

# The Lightsail container spec sets $PORT (deploy/activity.containers.json);
# default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
