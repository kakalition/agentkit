# Single-node agentkit image. Build: docker build -t agentkit .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENTKIT_HOME=/data \
    AGENTKIT_WEBUI_HOST=0.0.0.0 \
    AGENTKIT_A2A_HOST=0.0.0.0

WORKDIR /app

# Install the runtime first (better layer caching), then the package.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Agent state (db, artifacts, logs, skills) lives on a volume.
VOLUME ["/data"]
EXPOSE 8787 9000 8765

# Point AGENTKIT_BOOTSTRAP at your app module (e.g. app:app) when running.
CMD ["agentkit", "serve"]
