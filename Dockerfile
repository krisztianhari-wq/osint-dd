# osint-dd – szerveres futtatás a sadrobot infrán (Caddy + passkey-proxy mögött). Nem root, SQLCipher, DejaVu-betűk a PDF-hez.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Budapest \
    OSINTDD_HOME=/data OSINTDD_AUTH=proxy OSINTDD_BIND=0.0.0.0 OSINTDD_ALLOWED_EMAILS_FILE=/etc/osintdd/emails.txt

RUN apt-get update -q && apt-get install -y -q --no-install-recommends fonts-dejavu-core whois ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10005 --home /app osintdd && mkdir -p /data && chown osintdd /data
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY pyproject.toml README.md LICENSE ./
COPY osintdd ./osintdd
RUN pip install --no-cache-dir --no-deps . && rm -rf /root/.cache
USER osintdd
EXPOSE 8780
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8780/healthz',timeout=4)"
CMD ["osintdd", "gui", "--host", "0.0.0.0", "--port", "8780"]
