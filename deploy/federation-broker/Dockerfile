FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BROKER_DB_PATH=/var/lib/groundrecall-broker/broker.sqlite3 \
    BROKER_HOST=0.0.0.0 \
    BROKER_PORT=8765

WORKDIR /opt/groundrecall
COPY pyproject.toml README.md ./
COPY src ./src
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git \
    && python -m pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 groundrecall \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin groundrecall \
    && install -d -o 10001 -g 10001 -m 0700 /var/lib/groundrecall-broker

USER 10001:10001
EXPOSE 8765
VOLUME ["/var/lib/groundrecall-broker"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2)"]
ENTRYPOINT ["python", "-m", "groundrecall.federation_broker_server"]
CMD ["serve"]
