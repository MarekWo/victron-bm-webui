# victron-bm-webui

A lightweight, containerized web application for remote monitoring of a Victron BMV-712 Smart battery monitor over Bluetooth Low Energy (BLE).

## Features

- **Web Dashboard** — real-time battery status (voltage, current, power, SoC, temperature, consumed Ah, remaining time)
- **Trend Charts** — historical data visualization with selectable metrics and time ranges
- **Alarm Log** — searchable alarm history with time range filters, pagination, and notification status badges
- **System Info** — device status, BLE mode, database stats, SMTP config, alarm thresholds at a glance
- **Email & Push Alerts** — configurable SMTP and Pushover notifications for alarm conditions (low voltage, low SoC, temperature, device offline)
- **REST API** — JSON endpoints for integration with external systems
- **Offline-capable** — all frontend assets (Bootstrap 5, Chart.js) served locally
- **Responsive** — optimized for desktop, tablet, and mobile devices
- **Dockerized** — single-command deployment with docker-compose

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- For real BLE: Linux host with Bluetooth adapter

### Development Setup (Mock Mode)

1. Clone the repository:
   ```bash
   git clone https://github.com/MarekWo/victron-bm-webui.git
   cd victron-bm-webui
   ```

2. Create configuration files:
   ```bash
   cp .env.example .env
   cp config/config.yaml.example config/config.yaml
   ```

3. Build and run:
   ```bash
   docker compose up --build -d
   ```

4. Open http://localhost in your browser.

### Production Setup (Real BLE)

1. Clone and create configuration files:
   ```bash
   git clone https://github.com/MarekWo/victron-bm-webui.git
   cd victron-bm-webui
   cp .env.example .env
   cp config/config.yaml.example config/config.yaml
   ```

2. Edit `.env` — set BLE credentials and enable real device mode:
   ```
   DEVICE_MOCK=false
   BLE_MAC_ADDRESS=D8:AB:02:0C:FE:A4
   BLE_ADV_KEY=your_advertisement_key_hex
   COMPOSE_FILE=docker-compose.yml:docker-compose.ble.yml
   ```
   The advertisement key can be obtained from the VictronConnect app.

3. Optionally configure SMTP notifications in `.env`:
   ```
   SMTP_ENABLED=true
   SMTP_SERVER=smtp.example.com
   SMTP_PORT=587
   SMTP_USERNAME=user
   SMTP_PASSWORD=secret
   SMTP_SENDER_EMAIL=victron@example.com
   SMTP_RECIPIENTS=admin@example.com
   ```

4. Optionally adjust alarm thresholds and other behavior in `config/config.yaml`.

5. Build and run:
   ```bash
   docker compose up --build -d
   ```

The BLE override (`docker-compose.ble.yml`) adds `network_mode: host`, D-Bus access, and privileged mode required for Bluetooth on Linux.

### Stopping

```bash
docker compose down
```

## Configuration

Configuration is split into two files by purpose:

### `.env` — Infrastructure and Secrets

Contains Docker settings, device credentials, and SMTP/Pushover credentials. These are values that differ between environments and/or contain secrets.

| Variable                     | Default              | Description                          |
|------------------------------|----------------------|--------------------------------------|
| `TZ`                         | `Europe/Warsaw`      | Container timezone                   |
| `APP_PORT`                   | `80`                 | Listening port (also used inside container) |
| `DEVICE_MOCK`                | `true`               | Use mock data (`false` for real BLE) |
| `BLE_MAC_ADDRESS`            |                      | Victron device MAC address           |
| `BLE_ADV_KEY`                |                      | BLE advertisement encryption key     |
| `COMPOSE_FILE`               |                      | Set to `docker-compose.yml:docker-compose.ble.yml` for BLE |
| `SMTP_ENABLED`               | `false`              | Enable email notifications           |
| `SMTP_SERVER`                |                      | SMTP server hostname                 |
| `SMTP_PORT`                  | `587`                | SMTP server port                     |
| `SMTP_USE_TLS`               | `true`               | Use STARTTLS                         |
| `SMTP_USERNAME`              |                      | SMTP authentication username         |
| `SMTP_PASSWORD`              |                      | SMTP authentication password         |
| `SMTP_SENDER_NAME`           | `Victron BM Monitor` | Display name for outgoing emails     |
| `SMTP_SENDER_EMAIL`          |                      | Sender email address                 |
| `SMTP_RECIPIENTS`            |                      | Comma-separated recipient emails     |
| `PUSHOVER_ENABLED`           | `false`              | Enable Pushover push notifications   |
| `PUSHOVER_TOKEN`             |                      | Pushover application token           |
| `PUSHOVER_USER`              |                      | Pushover user/group key              |
| `PRIORITY_...`               |                      | Priorities for events (-2 to 2)      |

### `config/config.yaml` — Application Behavior

Contains settings that control how the application behaves. These typically stay the same across environments.

| Section         | Key Options                              | Description                              |
|-----------------|------------------------------------------|------------------------------------------|
| `device`        | `name`                                   | Device display name                      |
| `ble`           | `poll_interval_seconds`                  | BLE polling interval (default: 10s)      |
| `database`      | `path`, `retention_days`                 | SQLite storage (default: 30 days)        |
| `alarms`        | `low_voltage`, `low_soc`, etc.           | Alarm thresholds (set to `null` to disable) |
| `notifications` | `alarm_triggered`, `device_offline`, etc.| Which events trigger emails              |

See [`config/config.yaml.example`](config/config.yaml.example) for all options with defaults.

## BLE Reliability & Watchdog

BLE connections can stall over time due to BlueZ/D-Bus issues. The app has two layers of protection:

### Internal Watchdog (built-in)

The BLE reader detects stale connections (no data for 120s) and restarts the scanner. After `max_scanner_restarts` consecutive failures (default: 3), it terminates the process. Docker's `restart: unless-stopped` policy automatically restarts the container with a clean BLE stack.

The Dockerfile includes a `HEALTHCHECK` that monitors BLE connectivity — Docker marks the container as unhealthy after 5 minutes of disconnection.

### External Watchdog (systemd service)

For production, install the external watchdog for additional resilience:

```bash
cd /opt/victron-bm-webui/scripts/watchdog
sudo ./install.sh
```

The watchdog service:
- Checks container health every 30 seconds
- Restarts the container when Docker HEALTHCHECK reports unhealthy
- Resets the Bluetooth adapter (`hci0`) after 3 failed restarts in 10 minutes
- Sends email notifications on restart/BT reset (reads SMTP config from `.env`)
- Saves diagnostic logs before each restart to `/tmp/victron-bm-watchdog-*.log`
- Exposes a status endpoint at `http://localhost:5052/status`

### Email & Push Notifications

When SMTP and/or Pushover are configured in `.env`, the system sends alerts for:
- **DEVICE_OFFLINE** — no BLE data for 5 minutes (built-in alarm engine)
- **DEVICE_ONLINE** — BLE data resumes after offline (built-in alarm engine)
- **WATCHDOG restart** — container restarted due to unhealthy status (external watchdog)
- **WATCHDOG BT reset** — Bluetooth adapter reset after repeated failures (external watchdog)
- **Threshold alarms** — low voltage, low SoC, high temperature, AC power loss/restore, etc.

Pushover notifications can be fine-tuned using priority levels (-2 to 2) configured in `.env` (e.g., `PRIORITY_AC_POWER_LOST=1`, `PRIORITY_WATCHDOG_RESTART=2`).

Useful commands:
```bash
systemctl status victron-bm-watchdog       # Service status
tail -f /var/log/victron-bm-watchdog.log   # Watchdog logs
curl http://localhost:5052/status           # Container status (JSON)
curl http://localhost:5052/history          # Restart history
sudo ./install.sh --uninstall              # Remove
```

## REST API

| Endpoint              | Description                                      |
|-----------------------|--------------------------------------------------|
| `GET /api/v1/status`  | Current device state (voltage, current, SoC, etc.) |
| `GET /api/v1/history` | Historical readings (`?from=&to=&fields=&resolution=`) |
| `GET /api/v1/alarms`  | Alarm log entries (`?from=&to=&limit=`)          |
| `GET /api/v1/health`  | Health check (uptime, DB stats, BLE status)      |
| `GET /api/v1/config`  | Configuration info (thresholds, SMTP status)     |

## Technology Stack

- Python 3.11 / Flask / Gunicorn
- victron-ble + bleak (BLE communication)
- Chart.js 4.x (dual-axis time-series charts)
- Bootstrap 5.3 (dark theme) + Bootstrap Icons
- SQLite (WAL mode)
- Docker + docker-compose

## License

MIT
