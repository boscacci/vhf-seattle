FROM python:3.12-slim

ARG INSTALL_EXTRAS=dev,analysis,transcribe

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TALKINGBOATS_CLIP_DB_PATH=/data/live-transcripts.sqlite3 \
    TALKINGBOATS_TRANSCRIBE_SQLITE_PATH=/data/live-transcripts.sqlite3 \
    TALKINGBOATS_PROXY_PERFORMANCE_HISTORY_DB_PATH=/data/performance_telemetry.sqlite3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      ffmpeg \
      git \
      openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY public-site ./public-site
COPY scripts ./scripts
COPY docs ./docs

RUN if [ -n "${INSTALL_EXTRAS}" ]; then \
      pip install -e ".[${INSTALL_EXTRAS}]"; \
    else \
      pip install -e .; \
    fi

RUN useradd --create-home --uid 10001 talkingboats \
    && mkdir -p /data /outputs \
    && chown -R talkingboats:talkingboats /data /outputs /app

USER talkingboats

VOLUME ["/data", "/outputs"]

CMD ["talkingboats-live-radio-proxy", "--host", "0.0.0.0", "--port", "8095"]
