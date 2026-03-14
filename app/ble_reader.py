"""BLE reader thread for victron-bm-webui.

Reads data from a Victron BMV-712 Smart battery monitor via BLE,
or generates mock data for development when device.mock is enabled.
"""

import logging
import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


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
    ) -> None:
        super().__init__(daemon=True, name="ble-reader")
        self.config = config
        self.shared_state = shared_state
        self.db = db
        self._stop_event = threading.Event()
        self._mock_mode = config["device"].get("mock", False)
        self._poll_interval = config["ble"].get("poll_interval_seconds", 10)
        self._retention_days = config["database"].get("retention_days", 30)
        self._purge_counter = 0

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
                self._maybe_purge()
            except Exception:
                log.exception("Error generating mock data")

            self._stop_event.wait(self._poll_interval)

    def _run_real(self) -> None:
        """Read BLE data from the Victron device."""
        mac_address = self.config["device"].get("mac_address", "")
        adv_key = self.config["device"].get("advertisement_key", "")

        if not mac_address or not adv_key:
            log.error("BLE reader: mac_address and advertisement_key must be configured")
            return

        try:
            from victron_ble.scanner import Scanner
        except ImportError:
            log.error("victron-ble library not installed. Install with: pip install victron-ble")
            return

        log.info("BLE reader: scanning for device %s", mac_address)

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._ble_scan_loop(mac_address, adv_key))
        except Exception:
            log.exception("BLE scan loop failed")
        finally:
            loop.close()

    async def _ble_scan_loop(self, mac_address: str, adv_key: str) -> None:
        """Async BLE scanning loop using victron-ble."""
        from bleak import BleakScanner
        from victron_ble.devices import detect_device_type

        last_reading_time = 0.0

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
                self._maybe_purge()
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

        while not self._stop_event.is_set():
            await asyncio.sleep(1)

        await scanner.stop()

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
