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

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usar xvfb para ejecutar wkhtmltoimage en modo headless
CMD ["sh", "-c", "xvfb-run -a --server-args='-screen 0 1024x768x24' python hablemos.py"]