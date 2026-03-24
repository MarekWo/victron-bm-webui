FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for BLE (bluez, dbus)
RUN apt-get update && \
    apt-get install -y --no-install-recommends bluez libdbus-1-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

# Create data directory
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV APP_PORT=80
EXPOSE ${APP_PORT}

# Health check: verify BLE is connected via the health API.
# After start-period (120s for BLE init), check every 60s.
# Mark unhealthy after 5 consecutive failures (5 min of BLE disconnect).
HEALTHCHECK --interval=60s --timeout=10s --retries=5 --start-period=120s \
  CMD python -c "import urllib.request,json,sys;r=json.load(urllib.request.urlopen('http://localhost:'+__import__('os').environ.get('APP_PORT','80')+'/api/v1/health'));sys.exit(0 if r.get('ble',{}).get('connected') else 1)"

# Use exec so Gunicorn is PID 1 and receives signals directly from Docker
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${APP_PORT} --workers 1 --threads 2 'app:create_app()'"]
