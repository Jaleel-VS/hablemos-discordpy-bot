FROM python:3.12-slim-bookworm

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    xvfb \
    xauth \
    fonts-liberation \
    fontconfig \
    libraqm0 \
    && rm -rf /var/lib/apt/lists/*
# NOTE: xauth is required by xvfb-run; --no-install-recommends drops it, so it
# must be listed explicitly. Removing it breaks all wkhtmltoimage rendering.

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

# Use the image's Python (no downloads), precompile .pyc for faster boot, and
# copy files out of the cache mount instead of hardlinking into it.
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first so code edits don't invalidate this layer. --locked fails
# the build if uv.lock is out of date with pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

# Usar xvfb para ejecutar wkhtmltoimage en modo headless
CMD ["sh", "-c", "xvfb-run -a --server-args='-screen 0 1024x768x24' python hablemos.py"]