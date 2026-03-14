# victron-bm-webui

A lightweight, containerized web application for remote monitoring of a Victron BMV-712 Smart battery monitor over Bluetooth Low Energy (BLE).

## Features

- **Web Dashboard** — real-time battery status (voltage, current, power, SoC, temperature, consumed Ah, remaining time)
- **Trend Charts** — historical data visualization with selectable metrics and time ranges
- **Alarm Log** — searchable alarm history with time range filters, pagination, and notification status badges
- **System Info** — device status, BLE mode, database stats, SMTP config, alarm thresholds at a glance
- **Email Alerts** — configurable SMTP notifications for alarm conditions (low voltage, low SoC, temperature, device offline)
- **REST API** — JSON endpoints for integration with external systems
- **Offline-capable** — all frontend assets (Bootstrap 5, Chart.js) served locally
- **Responsive** — optimized for desktop, tablet, and mobile devices
- **Dockerized** — single-command deployment with docker-compose

## Current Status

**Stage 8** — Alarm Log & Info pages, SMTP via environment variables.

All four UI pages are complete: live dashboard, trend charts, alarm log with filters/pagination, and system info page. SMTP email settings can now be configured via `.env` environment variables (overriding `config.yaml`).

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### Setup

1. Clone the repository:
   ```bash
   git clone git@github.com:MarekWo/victron-bm-webui.git
   cd victron-bm-webui
   ```

2. Create your environment file:
   ```bash
   cp .env.example .env
   # Edit .env with timezone, port, and SMTP settings
   ```

3. Create your configuration file:
   ```bash
   cp config/config.yaml.example config/config.yaml
   # Edit config/config.yaml with your device settings
   ```

4. Build and run:
   ```bash
   docker compose up --build -d
   ```

5. Open http://localhost in your browser.

### Stopping

```bash
docker compose down
```

## Configuration

### Environment Variables (`.env`)

| Variable           | Default              | Description                          |
|--------------------|----------------------|--------------------------------------|
| `TZ`               | `Europe/Warsaw`      | Container timezone                   |
| `APP_PORT`         | `80`                 | Host port for the web interface      |
| `SMTP_ENABLED`     | (from config.yaml)   | Enable SMTP notifications (`true`/`false`) |
| `SMTP_SERVER`      | (from config.yaml)   | SMTP server hostname                 |
| `SMTP_PORT`        | `587`                | SMTP server port                     |
| `SMTP_USE_TLS`     | `true`               | Use STARTTLS                         |
| `SMTP_USERNAME`    | (from config.yaml)   | SMTP authentication username         |
| `SMTP_PASSWORD`    | (from config.yaml)   | SMTP authentication password         |
| `SMTP_SENDER_NAME` | `Victron BM Monitor` | Display name for outgoing emails     |
| `SMTP_SENDER_EMAIL`| (from config.yaml)   | Sender email address                 |
| `SMTP_RECIPIENTS`  | (from config.yaml)   | Comma-separated recipient emails     |

Environment variables override values from `config/config.yaml`.

### Application Config (`config/config.yaml`)

| Section         | Key Options                          | Description                              |
|-----------------|--------------------------------------|------------------------------------------|
| `device`        | `mac_address`, `advertisement_key`, `mock` | BMV-712 BLE device settings         |
| `ble`           | `poll_interval_seconds`              | BLE polling interval (default: 10s)      |
| `database`      | `path`, `retention_days`             | SQLite storage (default: 30 days)        |
| `alarms`        | `low_voltage`, `low_soc`, etc.       | Alarm thresholds (null to disable)       |
| `smtp`          | `server`, `port`, `use_tls`, etc.    | Email notification settings              |
| `notifications` | `alarm_triggered`, `device_offline`, etc. | Which events trigger emails         |

See `config/config.yaml.example` for all available options with defaults.

## REST API

| Endpoint              | Description                                      |
|-----------------------|--------------------------------------------------|
| `GET /api/v1/status`  | Current device state (voltage, current, SoC, etc.) |
| `GET /api/v1/history` | Historical readings (`?from=&to=&fields=&resolution=`) |
| `GET /api/v1/alarms`  | Alarm log entries (`?from=&to=&limit=`)          |
| `GET /api/v1/health`  | Health check (uptime, DB stats, BLE status)      |
| `GET /api/v1/config`  | Safe configuration info (thresholds, SMTP status) |

## Technology Stack

- Python 3.11 / Flask / Gunicorn
- victron-ble + bleak (BLE communication)
- Chart.js 4.x (dual-axis time-series charts)
- Bootstrap 5.3 (dark theme) + Bootstrap Icons
- SQLite (WAL mode)
- Docker + docker-compose

## License

TBD
