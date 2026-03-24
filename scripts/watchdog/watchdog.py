#!/usr/bin/env python3
"""
victron-bm-webui Container Watchdog

Monitors the victron-bm-webui Docker container and automatically restarts it
when the BLE connection to the Victron device is lost.
Designed to run as a systemd service on the host.

Features:
- Monitors container health status (Docker HEALTHCHECK)
- Automatically restarts unhealthy containers
- Resets BlueZ Bluetooth adapter after repeated restart failures
- Captures logs before restart for diagnostics
- HTTP endpoint for status check

Configuration via environment variables:
- VICTRON_DIR: Path to victron-bm-webui directory (default: /opt/victron-bm-webui)
- CHECK_INTERVAL: Seconds between checks (default: 30)
- LOG_FILE: Path to log file (default: /var/log/victron-bm-watchdog.log)
- HTTP_PORT: Port for status endpoint (default: 5052, 0 to disable)
- BT_ADAPTER: Bluetooth adapter name (default: hci0)
"""

import json
import os
import smtplib
import subprocess
import sys
import threading
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuration
VICTRON_DIR = os.environ.get("VICTRON_DIR", "/opt/victron-bm-webui")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/victron-bm-watchdog.log")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "5052"))
BT_ADAPTER = os.environ.get("BT_ADAPTER", "hci0")

CONTAINER_NAME = "victron-bm-webui"

# SMTP configuration (loaded from .env at startup)
smtp_config = {}

# Global state
last_check_time = None
last_check_result = {}
restart_history = []


def load_smtp_config() -> dict:
    """Load SMTP configuration from the project's .env file."""
    env_file = os.path.join(VICTRON_DIR, ".env")
    config = {}

    if not os.path.exists(env_file):
        return config

    env_vars = {}
    try:
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip("'\"")
    except Exception as e:
        log(f"Failed to read .env file: {e}", "WARN")
        return config

    config["enabled"] = env_vars.get("SMTP_ENABLED", "").lower() in ("true", "1", "yes")
    config["server"] = env_vars.get("SMTP_SERVER", "")
    config["port"] = int(env_vars.get("SMTP_PORT", "587") or "587")
    config["use_tls"] = env_vars.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    config["username"] = env_vars.get("SMTP_USERNAME", "")
    config["password"] = env_vars.get("SMTP_PASSWORD", "")
    config["sender_name"] = env_vars.get("SMTP_SENDER_NAME", "Victron BM Watchdog")
    config["sender_email"] = env_vars.get("SMTP_SENDER_EMAIL", "")
    recipients_str = env_vars.get("SMTP_RECIPIENTS", "")
    config["recipients"] = [r.strip() for r in recipients_str.split(",") if r.strip()]

    return config


def send_notification(subject: str, body: str) -> bool:
    """Send an email notification using SMTP config from .env."""
    if not smtp_config.get("enabled"):
        return False

    recipients = smtp_config.get("recipients", [])
    server_host = smtp_config.get("server", "")
    if not recipients or not server_host:
        return False

    sender_name = smtp_config.get("sender_name", "Victron BM Watchdog")
    sender_email = smtp_config.get("sender_email", "")

    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        port = smtp_config.get("port", 587)
        if smtp_config.get("use_tls", True):
            server = smtplib.SMTP(server_host, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(server_host, port, timeout=30)
            server.ehlo()

        username = smtp_config.get("username", "")
        password = smtp_config.get("password", "")
        if username and password:
            server.login(username, password)

        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        log(f"Email sent: {subject}")
        return True
    except Exception as e:
        log(f"Failed to send email: {e}", "ERROR")
        return False


def log(message: str, level: str = "INFO"):
    """Log message to file and stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, flush=True)

    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[{timestamp}] [ERROR] Failed to write to log file: {e}")


def run_command(args: list, timeout: int = 30) -> tuple:
    """Run a shell command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def run_compose_command(args: list, timeout: int = 60) -> tuple:
    """Run docker compose command in the victron directory."""
    try:
        result = subprocess.run(
            ["docker", "compose"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=VICTRON_DIR,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def get_container_status() -> dict:
    """Get container status including health."""
    success, stdout, stderr = run_command([
        "docker", "inspect",
        "--format", "{{.State.Status}}|{{.State.Health.Status}}|{{.State.StartedAt}}",
        CONTAINER_NAME,
    ])

    if not success:
        return {
            "name": CONTAINER_NAME,
            "exists": False,
            "status": "not_found",
            "health": "unknown",
            "error": stderr,
        }

    parts = stdout.split("|")
    status = parts[0] if len(parts) > 0 else "unknown"
    health = parts[1] if len(parts) > 1 else "none"
    started_at = parts[2] if len(parts) > 2 else ""

    if health in ("", "<no value>"):
        health = "none"

    return {
        "name": CONTAINER_NAME,
        "exists": True,
        "status": status,
        "health": health,
        "started_at": started_at,
    }


def get_container_logs(lines: int = 100) -> str:
    """Get recent container logs."""
    success, stdout, stderr = run_compose_command([
        "logs", "--tail", str(lines), CONTAINER_NAME,
    ])
    return stdout if success else f"Failed to get logs: {stderr}"


def restart_container() -> bool:
    """Restart the container using docker compose."""
    log(f"Restarting container: {CONTAINER_NAME}", "WARN")

    success, stdout, stderr = run_compose_command(
        ["restart", CONTAINER_NAME], timeout=120
    )

    if success:
        log(f"Container {CONTAINER_NAME} restarted successfully")
        return True
    else:
        log(f"Failed to restart {CONTAINER_NAME}: {stderr}", "ERROR")
        return False


def start_container() -> bool:
    """Start a stopped container using docker compose up."""
    log(f"Starting container: {CONTAINER_NAME}", "WARN")

    success, stdout, stderr = run_compose_command(
        ["up", "-d", CONTAINER_NAME], timeout=120
    )

    if success:
        log(f"Container {CONTAINER_NAME} started successfully")
        return True
    else:
        log(f"Failed to start {CONTAINER_NAME}: {stderr}", "ERROR")
        return False


def reset_bluetooth_adapter() -> bool:
    """Reset the Bluetooth adapter to recover from BlueZ/D-Bus stale state.

    Tries hciconfig reset first, then falls back to bluetoothctl power cycle.
    """
    log(f"Resetting Bluetooth adapter {BT_ADAPTER}", "WARN")

    # Method 1: hciconfig reset
    success, stdout, stderr = run_command(
        ["hciconfig", BT_ADAPTER, "reset"], timeout=10
    )
    if success:
        log(f"Bluetooth adapter {BT_ADAPTER} reset via hciconfig")
        time.sleep(3)
        return True

    log(f"hciconfig reset failed: {stderr}, trying bluetoothctl", "WARN")

    # Method 2: bluetoothctl power cycle
    run_command(["bluetoothctl", "power", "off"], timeout=10)
    time.sleep(2)
    success, stdout, stderr = run_command(
        ["bluetoothctl", "power", "on"], timeout=10
    )
    if success:
        log(f"Bluetooth adapter reset via bluetoothctl power cycle")
        time.sleep(3)
        return True

    log(f"Bluetooth adapter reset failed: {stderr}", "ERROR")
    return False


def count_recent_restarts(minutes: int = 10) -> int:
    """Count how many times the container was restarted in the last N minutes."""
    cutoff_time = time.time() - (minutes * 60)
    count = 0
    for entry in restart_history:
        if "restart_success" in entry:
            try:
                dt = datetime.fromisoformat(entry["timestamp"])
                if dt.timestamp() >= cutoff_time:
                    count += 1
            except ValueError:
                pass
    return count


def save_diagnostic(status: dict, reason: str) -> str:
    """Save diagnostic info before restart."""
    logs = get_container_logs(lines=200)
    diag_file = (
        f"/tmp/victron-bm-watchdog-{reason}-"
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    )
    try:
        with open(diag_file, "w") as f:
            f.write("=== Container Diagnostic Report ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"Container: {CONTAINER_NAME}\n")
            f.write(f"Status: {json.dumps(status, indent=2)}\n")
            f.write("\n=== Recent Logs ===\n")
            f.write(logs)
        log(f"Diagnostic info saved to: {diag_file}")
        return diag_file
    except Exception as e:
        log(f"Failed to save diagnostic info: {e}", "ERROR")
        return ""


def handle_unhealthy(status: dict):
    """Handle an unhealthy container — restart, escalate to BT reset if needed."""
    global restart_history

    log(f"Container {CONTAINER_NAME} is unhealthy! Health: {status['health']}", "WARN")

    diag_file = save_diagnostic(status, "unhealthy")

    recent = count_recent_restarts(minutes=10)
    restart_success = False

    bt_reset = False
    if recent >= 3:
        bt_reset = True
        log(
            f"{CONTAINER_NAME} restarted {recent} times in last 10 min — "
            f"resetting Bluetooth adapter before restart",
            "WARN",
        )
        # Stop container, reset BT, then start
        run_compose_command(["stop", CONTAINER_NAME], timeout=60)
        reset_bluetooth_adapter()
        restart_success = start_container()
    else:
        restart_success = restart_container()

    # Send email notification about the restart
    action = "Bluetooth adapter reset + container restart" if bt_reset else "container restart"
    send_notification(
        subject=f"[Victron BM] WATCHDOG — {action}",
        body=(
            f"The watchdog has performed a {action}.\n\n"
            f"Reason: BLE connection lost (container unhealthy)\n"
            f"Container: {CONTAINER_NAME}\n"
            f"Restart successful: {restart_success}\n"
            f"Recent restarts (last 10 min): {recent + 1}\n"
            f"Diagnostic file: {diag_file}\n"
            f"Timestamp: {datetime.now().isoformat()}\n\n"
            f"This is an automated alert from victron-bm-watchdog."
        ),
    )

    restart_history.append({
        "timestamp": datetime.now().isoformat(),
        "reason": "unhealthy",
        "status_before": status,
        "restart_success": restart_success,
        "bt_reset": bt_reset,
        "diagnostic_file": diag_file,
    })

    # Keep only last 50 entries
    if len(restart_history) > 50:
        restart_history[:] = restart_history[-50:]


def handle_stopped(status: dict):
    """Handle a stopped container — start it."""
    global restart_history

    log(f"Container {CONTAINER_NAME} is stopped! Status: {status['status']}", "WARN")

    start_success = start_container()

    send_notification(
        subject=f"[Victron BM] WATCHDOG — container was stopped, restarting",
        body=(
            f"The watchdog found the container stopped and started it.\n\n"
            f"Container: {CONTAINER_NAME}\n"
            f"Previous status: {status['status']}\n"
            f"Start successful: {start_success}\n"
            f"Timestamp: {datetime.now().isoformat()}\n\n"
            f"This is an automated alert from victron-bm-watchdog."
        ),
    )

    restart_history.append({
        "timestamp": datetime.now().isoformat(),
        "reason": "stopped",
        "action": "start",
        "status_before": status,
        "restart_success": start_success,
    })

    if len(restart_history) > 50:
        restart_history[:] = restart_history[-50:]


def check_container():
    """Check the container and take action if needed."""
    global last_check_time, last_check_result

    last_check_time = datetime.now().isoformat()
    status = get_container_status()
    last_check_result = status

    if not status["exists"]:
        log(f"Container {CONTAINER_NAME} not found", "WARN")
    elif status["status"] != "running":
        handle_stopped(status)
    elif status["health"] == "unhealthy":
        handle_unhealthy(status)

    return status


class WatchdogHandler(BaseHTTPRequestHandler):
    """HTTP request handler for watchdog status."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def send_json(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self.send_json({
                "status": "ok",
                "service": "victron-bm-watchdog",
                "check_interval": CHECK_INTERVAL,
                "last_check": last_check_time,
            })
        elif self.path == "/status":
            self.send_json({
                "last_check_time": last_check_time,
                "container": last_check_result,
                "restart_history_count": len(restart_history),
                "recent_restarts": restart_history[-10:] if restart_history else [],
            })
        elif self.path == "/history":
            self.send_json({"restart_history": restart_history})
        else:
            self.send_json({"error": "Not found"}, 404)


def run_http_server():
    """Run HTTP status server."""
    if HTTP_PORT <= 0:
        return

    try:
        server = HTTPServer(("0.0.0.0", HTTP_PORT), WatchdogHandler)
        log(f"HTTP status server started on port {HTTP_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"HTTP server error: {e}", "ERROR")


def main():
    """Main entry point."""
    log("=" * 60)
    log("victron-bm-webui Container Watchdog starting")
    log(f"  Project directory: {VICTRON_DIR}")
    log(f"  Check interval: {CHECK_INTERVAL}s")
    log(f"  Log file: {LOG_FILE}")
    log(f"  HTTP port: {HTTP_PORT if HTTP_PORT > 0 else 'disabled'}")
    log(f"  Bluetooth adapter: {BT_ADAPTER}")
    log(f"  Container: {CONTAINER_NAME}")
    log("=" * 60)

    # Load SMTP config from .env for email notifications
    global smtp_config
    smtp_config = load_smtp_config()
    if smtp_config.get("enabled"):
        log(f"  SMTP: enabled ({smtp_config.get('server')})")
    else:
        log("  SMTP: disabled (no email notifications)")

    # Verify project directory exists
    if not os.path.exists(VICTRON_DIR):
        log(f"WARNING: Project directory not found: {VICTRON_DIR}", "WARN")

    # Verify docker is available
    success, stdout, stderr = run_command(["docker", "--version"])
    if not success:
        log(f"ERROR: Docker not available: {stderr}", "ERROR")
        sys.exit(1)
    log(f"Docker version: {stdout}")

    # Start HTTP server in background thread
    if HTTP_PORT > 0:
        http_thread = threading.Thread(target=run_http_server, daemon=True)
        http_thread.start()

    # Main monitoring loop
    log("Starting monitoring loop...")
    try:
        while True:
            try:
                check_container()
            except Exception as e:
                log(f"Error during container check: {e}", "ERROR")

            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log("Shutting down...")


if __name__ == "__main__":
    main()
