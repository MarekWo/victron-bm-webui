#!/bin/bash
#
# victron-bm-webui Container Watchdog Installer
#
# Installs a systemd service that monitors the victron-bm-webui Docker
# container and automatically restarts it when BLE connectivity is lost.
#
# Usage: sudo ./install.sh [--uninstall]
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

if [ "$EUID" -ne 0 ]; then
    error "Please run as root: sudo $0"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VICTRON_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

SERVICE_NAME="victron-bm-watchdog"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_FILE="/var/log/victron-bm-watchdog.log"

# Uninstall
if [ "$1" == "--uninstall" ]; then
    info "Uninstalling ${SERVICE_NAME}..."

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        info "Service stopped"
    fi

    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl disable "$SERVICE_NAME"
        info "Service disabled"
    fi

    if [ -f "$SERVICE_FILE" ]; then
        rm "$SERVICE_FILE"
        systemctl daemon-reload
        info "Service file removed"
    fi

    echo -e "${GREEN}Uninstallation complete!${NC}"
    echo ""
    echo "Note: Log file preserved at: $LOG_FILE"
    echo "To remove logs: sudo rm $LOG_FILE"
    exit 0
fi

# Install
info "Installing ${SERVICE_NAME}..."
info "  victron-bm-webui directory: $VICTRON_DIR"

if [ ! -f "$SCRIPT_DIR/watchdog.py" ]; then
    error "watchdog.py not found in $SCRIPT_DIR"
fi

if ! command -v docker &> /dev/null; then
    error "Docker is not installed or not in PATH"
fi

# Create log file
if [ ! -f "$LOG_FILE" ]; then
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    info "Created log file: $LOG_FILE"
fi

# Create systemd service file with correct paths
info "Creating systemd service file..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=victron-bm-webui Container Watchdog
Documentation=https://github.com/MarekWo/victron-bm-webui
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
Environment=VICTRON_DIR=${VICTRON_DIR}
Environment=CHECK_INTERVAL=30
Environment=LOG_FILE=${LOG_FILE}
Environment=HTTP_PORT=5052
Environment=BT_ADAPTER=hci0
ExecStart=/usr/bin/python3 -u ${SCRIPT_DIR}/watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

info "Reloading systemd..."
systemctl daemon-reload

info "Enabling service..."
systemctl enable "$SERVICE_NAME"

info "Starting service..."
systemctl start "$SERVICE_NAME"

sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service is running!"

    if command -v curl &> /dev/null; then
        HEALTH=$(curl -s http://127.0.0.1:5052/health 2>/dev/null || echo "")
        if echo "$HEALTH" | grep -q '"status"'; then
            info "Health check passed!"
        else
            warn "Health check failed — service may still be starting"
        fi
    fi
else
    error "Service failed to start. Check: journalctl -u $SERVICE_NAME"
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "The watchdog monitors the victron-bm-webui container and will:"
echo "  - Check container health every 30 seconds"
echo "  - Restart the container if BLE is disconnected"
echo "  - Reset Bluetooth adapter after 3 failed restarts"
echo "  - Save diagnostic logs before each restart"
echo ""
echo "Useful commands:"
echo "  systemctl status $SERVICE_NAME        # Check service status"
echo "  sudo journalctl -u $SERVICE_NAME -f   # View service logs"
echo "  tail -f $LOG_FILE                     # View watchdog logs"
echo "  curl http://localhost:5052/status      # Check container status"
echo "  curl http://localhost:5052/history     # View restart history"
echo "  sudo $0 --uninstall                   # Uninstall"
echo ""
echo "Diagnostic files are saved to /tmp/victron-bm-watchdog-*.log"
