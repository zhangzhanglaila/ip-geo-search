FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IPGEOSEARCH_DATA_ROOT=/data

WORKDIR /app

COPY . .

RUN useradd --create-home --uid 10001 ipgeosearch \
    && mkdir -p /data \
    && chown -R ipgeosearch:ipgeosearch /app /data

VOLUME ["/data"]

USER ipgeosearch

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)"

CMD ["python", "api.py", "--host", "0.0.0.0", "--port", "8787"]
