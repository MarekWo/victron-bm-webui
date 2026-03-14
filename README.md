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

**Stage 0** — Project skeleton with Docker environment and placeholder UI.

The application currently serves a Bootstrap 5 dark-themed dashboard with navigation between four pages (Dashboard, Trends, Alarm Log, Info). No BLE communication or data storage yet.

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### Setup

1. Clone the repository:
   ```bash
   git clone git@github.com:<USERNAME>/victron-bm-webui.git
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

See `config/config.yaml.example` for all available options.

## Technology Stack

- Python 3.11 / Flask / Gunicorn
- Bootstrap 5.3 (dark theme) + Bootstrap Icons
- SQLite (planned)
- Docker + docker-compose

## License

TBD
