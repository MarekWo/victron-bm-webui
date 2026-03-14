# victron-bm-webui

A lightweight, containerized web application for remote monitoring of a Victron BMV-712 Smart battery monitor over Bluetooth Low Energy (BLE).

## Features

- **Web Dashboard** — real-time battery status (voltage, current, power, SoC, temperature, consumed Ah, remaining time)
- **Trend Charts** — historical data visualization with selectable metrics and time ranges
- **Email Alerts** — configurable SMTP notifications for alarm conditions (low voltage, low SoC, temperature, device offline)
- **REST API** — JSON endpoints for integration with external systems
- **Offline-capable** — all frontend assets (Bootstrap 5, Chart.js) served locally
- **Responsive** — optimized for desktop, tablet, and mobile devices
- **Dockerized** — single-command deployment with docker-compose

## Current Status

**Stage 3** — BLE reader with mock mode.

The application serves a Bootstrap 5 dark-themed dashboard with navigation between four pages (Dashboard, Trends, Alarm Log, Info). Full YAML configuration, SQLite database, and a background BLE reader thread are in place. Mock mode generates realistic battery data for development. Real BLE mode uses the `victron-ble` library to read from a BMV-712 Smart device.

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
   # Edit .env if needed (timezone, port)
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

| Variable   | Default         | Description                          |
|------------|-----------------|--------------------------------------|
| `TZ`       | `Europe/Warsaw` | Container timezone                   |
| `APP_PORT` | `80`            | Host port for the web interface      |

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

## Technology Stack

- Python 3.11 / Flask / Gunicorn
- victron-ble + bleak (BLE communication)
- Bootstrap 5.3 (dark theme) + Bootstrap Icons
- SQLite (WAL mode)
- Docker + docker-compose

## License

TBD
