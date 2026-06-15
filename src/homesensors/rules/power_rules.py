"""Power monitoring rules — overcurrent, voltage anomalies, and breaker trip detection."""
from __future__ import annotations

import collections
import statistics
from pathlib import Path
from typing import Any

import structlog
import yaml

from homesensors.config import settings
from homesensors.rules.engine import Alert

log = structlog.get_logger(__name__)

# Rolling window for anomaly detection
_ROLLING_WINDOW = 60  # keep last 60 readings per circuit


def _load_circuit_labels(path: Path) -> dict[str, dict]:
    """Load circuit_labels.yml → {circuit_id: {name, location, panel, amps}}."""
    if not path.exists():
        log.warning("power_rules.no_circuit_labels", path=str(path))
        return {}
    try:
        with path.open() as f:
            raw = yaml.safe_load(f) or {}
        labels = raw.get("circuits", {})
        log.info("power_rules.circuit_labels_loaded", count=len(labels))
        return labels
    except Exception:
        log.exception("power_rules.circuit_labels_load_error", path=str(path))
        return {}


class PowerRules:
    """Evaluate power readings against safety and anomaly thresholds.

    Detects:
      • Overcurrent (watts above threshold)              → WARNING to home/alerts/power/{id}
      • Statistical watt anomaly (>2 std dev from mean)  → WARNING to home/alerts/power/{id}
      • Voltage sag (<110V) or spike (>130V)             → WARNING to home/alerts/power/{id}
      • Breaker trip (load drops to ~0 after prior draw) → CRITICAL to home/alerts/breaker/{id}

    All power alerts include `circuit_name` and `location` in the data dict so
    BerkeleyAlarms can interpolate them into TTS announcements.
    """

    def __init__(self) -> None:
        # circuit_id → deque of recent watt readings
        self._history: dict[str, collections.deque] = {}
        # circuit_id → consecutive-zero counter (for breaker trip detection)
        self._zero_count: dict[str, int] = {}
        # circuit_id → whether we've already fired a breaker-trip alert this cycle
        self._breaker_tripped: dict[str, bool] = {}
        # Load human-readable circuit labels
        self._labels = _load_circuit_labels(settings.circuit_labels_path)

    # ── label helpers ────────────────────────────────────────────────────

    def _circuit_name(self, circuit_id: str) -> str:
        return self._labels.get(circuit_id, {}).get("name", circuit_id)

    def _circuit_location(self, circuit_id: str) -> str:
        return self._labels.get(circuit_id, {}).get("location", "")

    def _circuit_data(self, circuit_id: str, extra: dict | None = None) -> dict:
        """Build the standard data dict included in every power alert."""
        label = self._labels.get(circuit_id, {})
        data = {
            "circuit_name": label.get("name", circuit_id),
            "location": label.get("location", ""),
            "panel": label.get("panel", ""),
            "circuit_id": circuit_id,
        }
        if extra:
            data.update(extra)
        return data

    # ── evaluate ─────────────────────────────────────────────────────────

    def evaluate(self, reading: Any) -> list[Alert]:
        alerts: list[Alert] = []
        circuit = reading.circuit_id

        # ── Track history ─────────────────────────────────────────────
        if circuit not in self._history:
            self._history[circuit] = collections.deque(maxlen=_ROLLING_WINDOW)
            self._zero_count[circuit] = 0
            self._breaker_tripped[circuit] = False
        self._history[circuit].append(reading.watts)

        # ── Breaker trip detection ────────────────────────────────────
        # A breaker trip = watt draw falls to near-zero AFTER having had
        # a meaningful load. We require N consecutive near-zero readings
        # (not just a momentary dip) before alerting.
        history = self._history[circuit]
        zero_thresh = settings.breaker_trip_zero_watts_threshold
        prior_thresh = settings.breaker_trip_min_prior_watts
        trip_window = settings.breaker_trip_window

        if reading.watts <= zero_thresh:
            self._zero_count[circuit] += 1
        else:
            # Load restored — reset breaker state
            self._zero_count[circuit] = 0
            self._breaker_tripped[circuit] = False

        # Check if we should raise the breaker trip alarm
        if (
            self._zero_count[circuit] >= trip_window
            and not self._breaker_tripped[circuit]
            and len(history) >= trip_window + 2
        ):
            # Verify there was meaningful prior load
            prior_readings = list(history)[-(trip_window + 10): -trip_window]
            prior_max = max(prior_readings) if prior_readings else 0
            if prior_max >= prior_thresh:
                self._breaker_tripped[circuit] = True
                circuit_name = self._circuit_name(circuit)
                log.warning(
                    "power_rules.breaker_tripped",
                    circuit=circuit,
                    circuit_name=circuit_name,
                    prior_max_watts=prior_max,
                )
                alerts.append(Alert(
                    severity="WARNING",
                    source="power_rules",
                    sensor_type="breaker",         # routes to home/alerts/breaker/{id}
                    sensor_id=circuit,
                    message=f"{circuit_name} breaker has been tripped",
                    data=self._circuit_data(circuit, {
                        "breaker_tripped": True,
                        "prior_max_watts": round(prior_max, 1),
                    }),
                    cooldown_sec=3600,             # don't re-alert for 1 hr
                ))
                # Skip other checks for this reading
                return alerts

        # ── Total watts > threshold → overcurrent WARNING ─────────────
        if reading.watts > settings.power_overcurrent_watts:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=(
                    f"Overcurrent on {self._circuit_name(circuit)}: "
                    f"{reading.watts:.0f}W "
                    f"(threshold {settings.power_overcurrent_watts:.0f}W)"
                ),
                data=self._circuit_data(circuit, {
                    "watts": reading.watts,
                    "threshold": settings.power_overcurrent_watts,
                }),
            ))

        # ── Circuit watts anomaly (>2 std dev) ────────────────────────
        if len(history) >= 10:
            mean = statistics.mean(history)
            stdev = statistics.stdev(history)
            if stdev > 0 and abs(reading.watts - mean) > 2 * stdev:
                alerts.append(Alert(
                    severity="WARNING",
                    source="power_rules",
                    sensor_type="power",
                    sensor_id=circuit,
                    message=(
                        f"Anomalous draw on {self._circuit_name(circuit)}: "
                        f"{reading.watts:.0f}W (mean {mean:.0f}W ± {stdev:.0f})"
                    ),
                    data=self._circuit_data(circuit, {
                        "watts": reading.watts,
                        "mean": round(mean, 1),
                        "stdev": round(stdev, 1),
                    }),
                ))

        # ── Voltage sag (<110V) or spike (>130V) ─────────────────────
        if reading.voltage < settings.voltage_min:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=f"Voltage sag on {self._circuit_name(circuit)}: {reading.voltage:.1f}V",
                data=self._circuit_data(circuit, {"voltage": reading.voltage}),
            ))
        elif reading.voltage > settings.voltage_max:
            alerts.append(Alert(
                severity="WARNING",
                source="power_rules",
                sensor_type="power",
                sensor_id=circuit,
                message=f"Voltage spike on {self._circuit_name(circuit)}: {reading.voltage:.1f}V",
                data=self._circuit_data(circuit, {"voltage": reading.voltage}),
            ))

        return alerts
