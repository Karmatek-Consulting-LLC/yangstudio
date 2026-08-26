# Single-image build: the UI is compiled, then served by the API process.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# lxml and paramiko need a toolchain; drop it again to keep the image small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git build-essential libxml2-dev libxslt1-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/yangstudio backend/yangstudio
RUN pip install --no-cache-dir ./backend \
 && apt-get purge -y build-essential && apt-get autoremove -y

COPY --from=ui /ui/dist /app/frontend/dist

ENV YANGSTUDIO_DATA=/data \
    YANGSTUDIO_HOST=0.0.0.0 \
    YANGSTUDIO_PORT=8420 \
    YANGSTUDIO_STATIC=/app/frontend/dist
VOLUME ["/data"]
EXPOSE 8420

# Run as a non-root user; /data is a mounted volume it must own.
RUN useradd -m -u 1000 yang && mkdir -p /data && chown -R yang /data
USER yang

CMD ["python", "-m", "uvicorn", "yangstudio.app:app", "--host", "0.0.0.0", "--port", "8420"]
