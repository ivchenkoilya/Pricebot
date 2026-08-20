FROM node:22-alpine AS webapp-build
WORKDIR /webapp
COPY webapp/package.json ./
RUN npm install --no-audit --no-fund
COPY webapp/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=webapp-build /webapp/dist /app/webapp/dist
RUN mkdir -p /data/tmp /data/tmp/media /data/whisper-cache

CMD ["python", "main.py"]
