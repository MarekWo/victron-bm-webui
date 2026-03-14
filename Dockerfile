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

EXPOSE 80

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "1", "--threads", "2", "app:create_app()"]
