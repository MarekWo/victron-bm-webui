"""BLE reader thread for victron-bm-webui.

Reads data from a Victron BMV-712 Smart battery monitor via BLE,
or generates mock data for development when device.mock is enabled.
"""

import asyncio
import logging
import math
import os
import random
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# How long without a BLE reading before restarting the scanner
SCANNER_WATCHDOG_SECONDS = 120

# How long to wait before retrying after a scanner failure
SCANNER_RETRY_DELAY_SECONDS = 10

# How long to wait for scanner.stop() before giving up
SCANNER_STOP_TIMEOUT_SECONDS = 10


class SharedState:
    """Thread-safe container for the latest BLE reading."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._last_update: datetime | None = None
        self._connected: bool = False

    def update(self, data: dict[str, Any]) -> None:
        """Update the shared state with a new reading."""
        with self._lock:
            self._data = dict(data)
            self._last_update = datetime.now(timezone.utc)
            self._connected = True

    def get(self) -> dict[str, Any]:
        """Get a copy of the current state."""
        with self._lock:
            result = dict(self._data)
            result["last_update"] = (
                self._last_update.isoformat() if self._last_update else None
            )
            result["connected"] = self._connected
            return result

    def set_disconnected(self) -> None:
        """Mark the device as disconnected."""
        with self._lock:
            self._connected = False


class MockDataGenerator:
    """Generates realistic mock battery monitor data for development."""

    def __init__(self) -> None:
        self._base_voltage = 12.8
        self._base_soc = 75.0
        self._base_current = -2.5
        self._base_temperature = 22.0
        self._cycle_offset = random.uniform(0, 2 * math.pi)
        self._alarm_counter = 0

    def generate(self) -> dict[str, Any]:
        """Generate a single mock reading with realistic variation."""
        t = time.time() / 60.0 + self._cycle_offset

        # Simulate slow charge/discharge cycle over ~30 minutes
        cycle = math.sin(t * 0.2)

        voltage = self._base_voltage + cycle * 0.8 + random.gauss(0, 0.02)
        voltage = round(max(10.0, min(15.5, voltage)), 2)

        current = self._base_current + cycle * 5.0 + random.gauss(0, 0.1)
        current = round(current, 2)

        power = round(voltage * current, 2)

        soc = self._base_soc + cycle * 15.0 + random.gauss(0, 0.5)
        soc = round(max(0.0, min(100.0, soc)), 1)

        consumed_ah = round((100.0 - soc) * 2.0, 1)

        if current < 0:
            remaining_mins = int(abs(soc / current) * 60) if current != 0 else 65535
        else:
            remaining_mins = 65535

        temperature = self._base_temperature + math.sin(t * 0.05) * 3.0
        temperature = round(temperature + random.gauss(0, 0.3), 1)

        # Occasional alarm simulation (every ~50 readings)
        self._alarm_counter += 1
        alarm = None
        if self._alarm_counter >= 50:
            alarm = "LOW_VOLTAGE" if voltage < 12.0 else None
            if alarm:
                self._alarm_counter = 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "voltage": voltage,
            "current": current,
            "power": power,
            "soc": soc,
            "consumed_ah": consumed_ah,
            "remaining_mins": remaining_mins,
            "temperature": temperature,
            "alarm": alarm,
        }


class BLEReaderThread(threading.Thread):
    """Background thread that reads BLE data or generates mock data."""

    def __init__(
        self,
        config: dict[str, Any],
        shared_state: SharedState,
        db: Any,
        alarm_engine: Any = None,
    ) -> None:
        super().__init__(daemon=True, name="ble-reader")
        self.config = config
        self.shared_state = shared_state
        self.db = db
        self.alarm_engine = alarm_engine
        self._stop_event = threading.Event()
        self._mock_mode = config["device"].get("mock", False)
        self._poll_interval = config["ble"].get("poll_interval_seconds", 10)
        self._retention_days = config["database"].get("retention_days", 30)
        self._purge_counter = 0
        self._max_restarts = config["ble"].get("max_scanner_restarts", 3)
        self._consecutive_failures = 0

    def run(self) -> None:
        """Main loop: read BLE data or generate mock data."""
        if self._mock_mode:
            log.info("BLE reader starting in MOCK mode (interval: %ds)", self._poll_interval)
            self._run_mock()
        else:
            log.info("BLE reader starting in REAL mode (interval: %ds)", self._poll_interval)
            self._run_real()

    def stop(self) -> None:
        """Signal the thread to stop."""
        self._stop_event.set()

    def _run_mock(self) -> None:
        """Generate mock data at the configured interval."""
        generator = MockDataGenerator()

        while not self._stop_event.is_set():
            try:
                data = generator.generate()
                self.shared_state.update(data)
                self.db.insert_reading(data)
                self._evaluate_alarms(data)
                self._check_offline()
                self._maybe_purge()
            except Exception:
                log.exception("Error generating mock data")

            self._stop_event.wait(self._poll_interval)

    def _run_real(self) -> None:
        """Read BLE data from the Victron device with auto-restart on failure."""
        mac_address = self.config["device"].get("mac_address", "")
        adv_key = self.config["device"].get("advertisement_key", "")

        if not mac_address or not adv_key:
            log.error("BLE reader: mac_address and advertisement_key must be configured")
            return

        try:
            from victron_ble.scanner import Scanner  # noqa: F401
        except ImportError:
            log.error("victron-ble library not installed. Install with: pip install victron-ble")
            return

        # Outer retry loop — restarts the scanner on failure or watchdog timeout
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            log.info(
                "BLE reader: starting scanner for %s (attempt %d)",
                mac_address, attempt,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(self._ble_scan_loop(mac_address, adv_key))
            except Exception:
                log.exception("BLE scan loop failed")
            finally:
                # Force-close all pending tasks to prevent event loop leaks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

                # Reset bleak's global D-Bus manager to clear stale state
                try:
                    from bleak.backends.bluezdbus import manager as _mgr
                    _mgr._global_instances.clear()
                    log.debug("Cleared bleak D-Bus manager cache")
                except Exception:
                    pass  # Not critical — best effort cleanup

            if self._stop_event.is_set():
                break

            self._consecutive_failures += 1
            self.shared_state.set_disconnected()

            if self._consecutive_failures >= self._max_restarts:
                log.critical(
                    "BLE recovery failed after %d consecutive attempts — "
                    "terminating process for container restart",
                    self._consecutive_failures,
                )
                # Give log time to flush
                time.sleep(1)
                os.kill(os.getpid(), signal.SIGTERM)
                return

            log.warning(
                "BLE scanner stopped (failure %d/%d), restarting in %ds...",
                self._consecutive_failures,
                self._max_restarts,
                SCANNER_RETRY_DELAY_SECONDS,
            )
            self._stop_event.wait(SCANNER_RETRY_DELAY_SECONDS)

    async def _ble_scan_loop(self, mac_address: str, adv_key: str) -> None:
        """Async BLE scanning loop with watchdog for stall detection."""
        from bleak import BleakScanner
        from victron_ble.devices import detect_device_type

        last_reading_time = time.time()

        def callback(device: Any, advertisement_data: Any) -> None:
            nonlocal last_reading_time

            if device.address.upper() != mac_address.upper():
                return

            now = time.time()
            if now - last_reading_time < self._poll_interval:
                return

            try:
                raw_data = advertisement_data.manufacturer_data.get(0x02E1)
                if raw_data is None:
                    return

                device_class = detect_device_type(raw_data)
                if device_class is None:
                    return

                parsed_device = device_class(advertisement_key=adv_key)
                parsed_data = parsed_device.parse(raw_data)

                alarm_val = parsed_data.get_alarm()
                alarm_str = alarm_val.name if alarm_val and alarm_val.value != 0 else None

                remaining = parsed_data.get_remaining_mins()
                if remaining is not None and remaining >= 65535:
                    remaining = None

                data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "voltage": parsed_data.get_voltage(),
                    "current": parsed_data.get_current(),
                    "power": round(
                        (parsed_data.get_voltage() or 0) * (parsed_data.get_current() or 0), 2
                    ),
                    "soc": parsed_data.get_soc(),
                    "consumed_ah": parsed_data.get_consumed_ah(),
                    "remaining_mins": remaining,
                    "temperature": parsed_data.get_temperature(),
                    "alarm": alarm_str,
                }

                self.shared_state.update(data)
                self.db.insert_reading(data)
                self._evaluate_alarms_async(data)
                self._maybe_purge()
                self._consecutive_failures = 0
                last_reading_time = now

                log.debug(
                    "BLE reading: V=%.2f I=%.2f SoC=%.1f%%",
                    data["voltage"] or 0,
                    data["current"] or 0,
                    data["soc"] or 0,
                )
            except Exception:
                log.exception("Error parsing BLE advertisement")

        scanner = BleakScanner(detection_callback=callback)
        await scanner.start()
        log.info("BLE scanner started, waiting for advertisements...")

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1)

                # Periodically check for offline condition
                self._check_offline()

                # Watchdog: if no reading for too long, restart scanner
                elapsed = time.time() - last_reading_time
                if elapsed > SCANNER_WATCHDOG_SECONDS:
                    log.warning(
                        "BLE watchdog: no data for %ds, restarting scanner",
                        int(elapsed),
                    )
                    self.shared_state.set_disconnected()
                    break
        finally:
            try:
                await asyncio.wait_for(scanner.stop(), timeout=SCANNER_STOP_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                log.warning("BLE scanner.stop() timed out after %ds, forcing restart",
                            SCANNER_STOP_TIMEOUT_SECONDS)
            except Exception:
                log.warning("BLE scanner.stop() failed (ignored)", exc_info=True)

    def _evaluate_alarms(self, data: dict[str, Any]) -> None:
        """Evaluate alarm conditions for the current reading (synchronous)."""
        if self.alarm_engine is not None:
            try:
                self.alarm_engine.evaluate(data)
            except Exception:
                log.exception("Error evaluating alarms")

    def _evaluate_alarms_async(self, data: dict[str, Any]) -> None:
        """Evaluate alarms in a separate thread to avoid blocking the event loop.

        This is used from the BLE callback which runs inside the async event loop.
        Blocking operations (like SMTP email sending) would stall the scanner.
        """
        if self.alarm_engine is not None:
            t = threading.Thread(
                target=self._evaluate_alarms,
                args=(data,),
                daemon=True,
                name="alarm-eval",
            )
            t.start()

    def _check_offline(self) -> None:
        """Delegate offline check to the alarm engine."""
        if self.alarm_engine is not None:
            try:
                self.alarm_engine.check_offline()
            except Exception:
                log.exception("Error checking offline status")

    def _maybe_purge(self) -> None:
        """Run retention purge every 100 readings."""
        self._purge_counter += 1
        if self._purge_counter >= 100:
            self._purge_counter = 0
            try:
                self.db.purge_old_readings(self._retention_days)
                self.db.purge_old_alarms(self._retention_days)
            except Exception:
                log.exception("Error during retention purge")
