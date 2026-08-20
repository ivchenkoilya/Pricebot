FROM node:22-bookworm-slim AS webapp-build
WORKDIR /webapp
COPY webapp/package.json ./
RUN npm install --no-audit --no-fund
COPY webapp/ ./
RUN npm run build

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp now needs a modern JS runtime for YouTube challenge solving.
# Reuse the already-pulled Node 22 runtime from the frontend build stage.
COPY --from=webapp-build /usr/local/bin/node /usr/local/bin/node
RUN node --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=webapp-build /webapp/dist /app/webapp/dist
RUN mkdir -p /data/tmp /data/tmp/media /data/whisper-cache

CMD ["python", "main.py"]
