"""AC mains presence detection for victron-bm-webui.

A BMV-712 is a shunt — it has no AC input and therefore no direct way of
telling whether mains power is present. The state has to be inferred from
what the shunt does measure: battery voltage and battery current.

Current is the stronger of the two signals, and it is stronger in both
directions. The moment mains disappears the inverter starts drawing from the
battery and current goes firmly negative — long before voltage has had time
to sag. The moment mains returns the charger starts pushing current in, which
is just as unambiguous, and far faster than waiting for terminal voltage to
climb back over `voltage_on`: measured on a real 60 A cut, loss was confirmed
in ~30 s but restoration took ~3 minutes, with the charger already delivering
8.7 A while this tracker still reported "on battery". Out of a deep discharge
the charger sits in constant-current bulk and that lag grows to tens of
minutes, which is long enough to shut hosts down after power is already back.

Voltage remains the fallback signal, with a hysteresis band so that a brief
sag cannot flip the state on its own.

The charge-current rule assumes the only thing charging the bank is a
mains-fed charger. If an independent DC source can charge it — solar/MPPT,
an alternator — set `ac_detection.charge_current` to 0 to switch the rule off
and fall back to voltage alone.
"""

from datetime import datetime, timezone
from typing import Any

# Used when neither `ac_detection` nor `alarms.ac_power_voltage` is configured.
DEFAULT_VOLTAGE_ON = 13.55
DEFAULT_VOLTAGE_OFF = 13.40
DEFAULT_DISCHARGE_CURRENT = -1.0
DEFAULT_DEBOUNCE_SAMPLES = 2

# Charging harder than this means a mains-fed charger is running. Set to 0 to
# disable when an independent DC source (solar/MPPT) can also charge the bank.
DEFAULT_CHARGE_CURRENT = 2.0

# Width of the hysteresis band derived from a legacy `alarms.ac_power_voltage`.
LEGACY_HYSTERESIS_VOLTS = 0.2


def resolve_ac_detection(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the effective ac_detection settings from a loaded config.

    `voltage_on` / `voltage_off` may be left unset, in which case they are
    derived from the legacy `alarms.ac_power_voltage` threshold: that value
    becomes the restore threshold and the loss threshold sits
    LEGACY_HYSTERESIS_VOLTS below it. Without either, hard defaults apply.

    Returns:
        Dict with voltage_on, voltage_off, discharge_current, debounce_samples.
    """
    detection = dict(config.get("ac_detection") or {})
    legacy = (config.get("alarms") or {}).get("ac_power_voltage")

    voltage_on = detection.get("voltage_on")
    voltage_off = detection.get("voltage_off")

    if voltage_on is None:
        voltage_on = float(legacy) if legacy is not None else DEFAULT_VOLTAGE_ON
    if voltage_off is None:
        voltage_off = (
            float(legacy) - LEGACY_HYSTERESIS_VOLTS
            if legacy is not None
            else DEFAULT_VOLTAGE_OFF
        )

    voltage_on = float(voltage_on)
    voltage_off = float(voltage_off)

    # A non-existent or inverted band would make the state flap on every
    # reading; collapse it back into a sane hysteresis window.
    if voltage_off >= voltage_on:
        voltage_off = voltage_on - LEGACY_HYSTERESIS_VOLTS

    discharge_current = detection.get("discharge_current")
    discharge_current = (
        float(discharge_current)
        if discharge_current is not None
        else DEFAULT_DISCHARGE_CURRENT
    )

    charge_current = detection.get("charge_current")
    charge_current = (
        float(charge_current)
        if charge_current is not None
        else DEFAULT_CHARGE_CURRENT
    )
    # A negative value here would make every discharge read as "mains back".
    charge_current = max(0.0, charge_current)

    debounce = detection.get("debounce_samples")
    debounce = int(debounce) if debounce is not None else DEFAULT_DEBOUNCE_SAMPLES
    debounce = max(1, debounce)

    return {
        "voltage_on": voltage_on,
        "voltage_off": voltage_off,
        "discharge_current": discharge_current,
        "charge_current": charge_current,
        "debounce_samples": debounce,
    }


class ACStateTracker:
    """Tracks mains presence across readings, with hysteresis and debounce."""

    def __init__(self, config: dict[str, Any]) -> None:
        settings = resolve_ac_detection(config)
        self.voltage_on: float = settings["voltage_on"]
        self.voltage_off: float = settings["voltage_off"]
        self.discharge_current: float = settings["discharge_current"]
        self.charge_current: float = settings["charge_current"]
        self.debounce_samples: int = settings["debounce_samples"]

        self._state: bool | None = None  # None = unknown (no usable reading yet)
        self._since: str | None = None
        self._pending: bool | None = None
        self._pending_count: int = 0

    @property
    def state(self) -> bool | None:
        """Current mains presence: True = on mains, False = on battery."""
        return self._state

    @property
    def since(self) -> str | None:
        """ISO 8601 timestamp of the last confirmed state change."""
        return self._since

    def update(self, voltage: float | None, current: float | None) -> bool | None:
        """Feed a new reading and return the (possibly updated) mains state.

        Args:
            voltage: Battery voltage in volts, or None if unavailable.
            current: Battery current in amps (negative = discharging),
                     or None if unavailable.

        Returns:
            True on mains, False on battery, None while still unknown.
        """
        raw = self._classify(voltage, current)

        if raw is None:
            # Unusable reading or inside the hysteresis band — hold the state
            # and drop any half-finished transition.
            self._pending = None
            self._pending_count = 0
            return self._state

        if self._state is None:
            # First usable reading: adopt it silently, no transition fired.
            self._set_state(raw)
            return self._state

        if raw == self._state:
            self._pending = None
            self._pending_count = 0
            return self._state

        if self._pending is raw:
            self._pending_count += 1
        else:
            self._pending = raw
            self._pending_count = 1

        if self._pending_count >= self.debounce_samples:
            self._set_state(raw)

        return self._state

    def _classify(self, voltage: float | None, current: float | None) -> bool | None:
        """Classify a single reading without any state or debounce logic."""
        if current is not None and current <= self.discharge_current:
            # Drawing meaningful current out of the battery — mains is gone,
            # regardless of what voltage still reads.
            return False

        if (self.charge_current > 0 and current is not None
                and current >= self.charge_current):
            # Something is pushing charge into the bank, and the only thing
            # that can be is the mains-fed charger. Trusting this instead of
            # waiting for voltage is what keeps restoration fast out of a deep
            # discharge, where terminal voltage stays low for a long while.
            return True

        if voltage is None:
            return None

        if voltage < self.voltage_off:
            return False
        if voltage >= self.voltage_on:
            return True

        # Between the two thresholds: ambiguous, hold whatever we had.
        return None

    def _set_state(self, state: bool) -> None:
        self._state = state
        self._since = datetime.now(timezone.utc).isoformat()
        self._pending = None
        self._pending_count = 0
