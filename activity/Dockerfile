# Multi-stage build: compile the Vite SPA with Node, then run FastAPI (which
# serves the built static files + /api) on Python. One image, one service.

# --- Stage 1: build the frontend ---------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /build/frontend

# The client bundle needs the Discord client id at *build* time (Vite inlines
# VITE_* vars). Railway passes it as a build arg.
ARG VITE_DISCORD_CLIENT_ID
ENV VITE_DISCORD_CLIENT_ID=$VITE_DISCORD_CLIENT_ID

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime -------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Bring the built SPA in where the backend expects it (ACTIVITY_STATIC_DIR
# default is ../static relative to app/, i.e. /app/static).
COPY --from=frontend /build/frontend/dist ./static

# Railway sets $PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
