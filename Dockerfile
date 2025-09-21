FROM python:3.11-slim-bullseye

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    xvfb \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usar xvfb para ejecutar wkhtmltoimage en modo headless
CMD ["sh", "-c", "xvfb-run -a --server-args='-screen 0 1024x768x24' python hablemos.py"]