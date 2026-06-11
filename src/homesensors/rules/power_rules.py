"""Power monitoring rules — overcurrent, voltage anomalies, circuit anomalies."""

from __future__ import annotations

import collections
import statistics
from typing import Any

import structlog

from homesensors.config import settings
from homesensors.rules.engine import Alert

log = structlog.get_logger(__name__)

# Rolling window for anomaly detection
_ROLLING_WINDOW = 60  # keep last 60 readings per circuit


class PowerRules:
    """Evaluate power readings against safety and anomaly thresholds."""

    def __init__(self) -> None:
        # circuit_id → deque of recent watt readings
        self._history: dict[str, collections.deque] = {}

    def evaluate(self, reading: Any) -> list[Alert]:
        alerts: list[Alert] = []
        circuit = reading.circuit_id

        # Track history for anomaly detection
        if circuit not in self._history:
            self._history[circuit] = collections.deque(maxlen=_ROLLING_WINDOW)
        self._history[circuit].append(reading.watts)

        # ── Total watts > threshold → overcurrent WARNING ──────────────
        if reading.watts > settings.power_overcurrent_watts:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=f"Overcurrent on {circuit}: {reading.watts:.0f}W (threshold {settings.power_overcurrent_watts:.0f}W)",
                data={"watts": reading.watts, "threshold": settings.power_overcurrent_watts},
            ))

        # ── Circuit watts anomaly (>2 std dev) ─────────────────────────
        history = self._history[circuit]
        if len(history) >= 10:
            mean = statistics.mean(history)
            stdev = statistics.stdev(history)
            if stdev > 0 and abs(reading.watts - mean) > 2 * stdev:
                alerts.append(Alert(
                    severity="WARNING",
                    source="power_rules",
                    sensor_type="power",
                    sensor_id=circuit,
                    message=f"Anomalous draw on {circuit}: {reading.watts:.0f}W (mean {mean:.0f}W ± {stdev:.0f})",
                    data={"watts": reading.watts, "mean": mean, "stdev": stdev},
                ))

        # ── Voltage sag (<110V) or spike (>130V) ──────────────────────
        if reading.voltage < settings.voltage_min:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=f"Voltage sag on {circuit}: {reading.voltage:.1f}V",
                data={"voltage": reading.voltage},
            ))
        elif reading.voltage > settings.voltage_max:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=f"Voltage spike on {circuit}: {reading.voltage:.1f}V",
                data={"voltage": reading.voltage},
            ))

        return alerts
