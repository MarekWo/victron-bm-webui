"""Alarm engine for victron-bm-webui.

Evaluates current readings against configured thresholds and device alarm state.
Logs alarm events and triggers email notifications with cooldown management.
"""

import logging
import time
from typing import Any

from app.mail import send_email
from app.models import Database

log = logging.getLogger(__name__)

# Cooldown period in seconds (15 minutes per alarm type)
COOLDOWN_SECONDS = 15 * 60

# Offline threshold: no data for 5 minutes
OFFLINE_THRESHOLD_SECONDS = 5 * 60


class AlarmEngine:
    """Evaluates alarm conditions and manages notifications."""

    def __init__(
        self,
        config: dict[str, Any],
        db: Database,
    ) -> None:
        self.config = config
        self.db = db
        self._alarm_config = config.get("alarms", {})
        self._smtp_config = config.get("smtp", {})
        self._notif_config = config.get("notifications", {})
        self._cooldowns: dict[str, float] = {}
        self._previous_device_alarm: str | None = None
        self._device_offline: bool = False
        self._last_data_time: float = 0.0

    def evaluate(self, data: dict[str, Any]) -> None:
        """Evaluate a new reading for alarm conditions.

        Args:
            data: Reading dictionary with voltage, current, soc, temperature, alarm, etc.
        """
        self._last_data_time = time.time()

        # If device was offline, it's back online
        if self._device_offline:
            self._device_offline = False
            if self._notif_config.get("device_online", True):
                self._fire_alarm(
                    "DEVICE_ONLINE",
                    "Device is back online and sending data.",
                )

        # Check device alarm state (from BLE device itself)
        device_alarm = data.get("alarm")
        self._check_device_alarm(device_alarm)

        # Check app-defined thresholds
        self._check_thresholds(data)

    def check_offline(self) -> None:
        """Check if the device has gone offline (no data for >5 minutes).

        Should be called periodically from the BLE reader loop.
        """
        if self._last_data_time == 0.0:
            return

        elapsed = time.time() - self._last_data_time
        if elapsed > OFFLINE_THRESHOLD_SECONDS and not self._device_offline:
            self._device_offline = True
            if self._notif_config.get("device_offline", True):
                mins = int(elapsed / 60)
                self._fire_alarm(
                    "DEVICE_OFFLINE",
                    f"No BLE data received for {mins} minutes.",
                )

    def _check_device_alarm(self, alarm: str | None) -> None:
        """Check for device alarm state changes."""
        prev = self._previous_device_alarm
        self._previous_device_alarm = alarm

        if alarm and alarm != prev:
            # New alarm or alarm changed
            if self._notif_config.get("alarm_triggered", True):
                self._fire_alarm(
                    f"DEVICE_{alarm}",
                    f"Device alarm triggered: {alarm}",
                )
        elif not alarm and prev:
            # Alarm cleared
            if self._notif_config.get("alarm_cleared", True):
                self._fire_alarm(
                    "ALARM_CLEARED",
                    f"Device alarm cleared (was: {prev}).",
                )

    def _check_thresholds(self, data: dict[str, Any]) -> None:
        """Check app-defined thresholds against current reading."""
        checks = [
            ("low_voltage", "voltage", "lt",
             lambda v, t: f"Battery voltage {v:.2f}V is below threshold {t}V"),
            ("high_voltage", "voltage", "gt",
             lambda v, t: f"Battery voltage {v:.2f}V exceeds threshold {t}V"),
            ("low_soc", "soc", "lt",
             lambda v, t: f"State of Charge {v:.1f}% is below threshold {t}%"),
            ("high_temperature", "temperature", "gt",
             lambda v, t: f"Temperature {v:.1f}\u00B0C exceeds threshold {t}\u00B0C"),
            ("low_temperature", "temperature", "lt",
             lambda v, t: f"Temperature {v:.1f}\u00B0C is below threshold {t}\u00B0C"),
        ]

        if not self._notif_config.get("threshold_exceeded", True):
            return

        for threshold_key, data_key, direction, msg_fn in checks:
            threshold = self._alarm_config.get(threshold_key)
            if threshold is None:
                continue

            value = data.get(data_key)
            if value is None:
                continue

            exceeded = (
                (direction == "lt" and value < threshold) or
                (direction == "gt" and value > threshold)
            )

            if exceeded:
                alarm_type = f"THRESHOLD_{threshold_key.upper()}"
                message = msg_fn(value, threshold)
                self._fire_alarm(alarm_type, message)

    def _fire_alarm(self, alarm_type: str, message: str) -> None:
        """Log an alarm and optionally send email notification.

        Respects cooldown period per alarm type.
        """
        now = time.time()
        last_fired = self._cooldowns.get(alarm_type, 0.0)

        if now - last_fired < COOLDOWN_SECONDS:
            return

        self._cooldowns[alarm_type] = now

        # Send email
        notified = send_email(
            self._smtp_config,
            subject=f"[Victron BM] {alarm_type}",
            body=f"{message}\n\nThis is an automated alert from victron-bm-webui.",
        )

        # Log to database
        try:
            self.db.insert_alarm(alarm_type, message, notified=notified)
        except Exception:
            log.exception("Failed to log alarm: %s", alarm_type)

        log.warning("ALARM %s: %s (notified=%s)", alarm_type, message, notified)
