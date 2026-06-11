"""Climate comfort rules — temperature, humidity, HVAC anomalies."""

from __future__ import annotations

from typing import Any

import structlog

from homesensors.config import settings
from homesensors.rules.engine import Alert

log = structlog.get_logger(__name__)

# Differential threshold between rooms that suggests HVAC issue
_TEMP_DIFFERENTIAL_F = 8.0


class ClimateRules:
    """Evaluate indoor climate readings against comfort thresholds."""

    def __init__(self) -> None:
        # Track latest temp per room for cross-room differential check
        self._room_temps: dict[str, float] = {}

    def evaluate(self, reading: Any) -> list[Alert]:
        alerts: list[Alert] = []
        room = reading.room_id
        temp = reading.temp_f
        humidity = reading.humidity_pct
        self._room_temps[room] = temp

        # ── Temperature outside comfort zone (65-78°F) ────────────────
        if temp < settings.comfort_temp_min_f:
            alerts.append(Alert(
                severity="INFO",
                source="climate_rules",
                sensor_type="climate",
                sensor_id=room,
                message=f"{room} too cold: {temp:.1f}°F (min {settings.comfort_temp_min_f}°F)",
                data={"temp_f": temp, "room_id": room},
            ))
        elif temp > settings.comfort_temp_max_f:
            alerts.append(Alert(
                severity="INFO",
                source="climate_rules",
                sensor_type="climate",
                sensor_id=room,
                message=f"{room} too warm: {temp:.1f}°F (max {settings.comfort_temp_max_f}°F)",
                data={"temp_f": temp, "room_id": room},
            ))

        # ── Humidity > 65% → mold risk ────────────────────────────────
        if humidity > settings.humidity_mold_threshold:
            alerts.append(Alert(
                severity="WARNING",
                source="climate_rules",
                sensor_type="climate",
                sensor_id=room,
                message=f"Mold risk in {room}: {humidity:.1f}% humidity",
                data={"humidity_pct": humidity, "room_id": room},
            ))

        # ── Large temp differential between rooms → HVAC issue ────────
        if len(self._room_temps) >= 2:
            temps = list(self._room_temps.values())
            diff = max(temps) - min(temps)
            if diff > _TEMP_DIFFERENTIAL_F:
                coldest = min(self._room_temps, key=self._room_temps.get)  # type: ignore[arg-type]
                warmest = max(self._room_temps, key=self._room_temps.get)  # type: ignore[arg-type]
                alerts.append(Alert(
                    severity="INFO",
                    source="climate_rules",
                    sensor_type="climate",
                    sensor_id="hvac",
                    message=f"HVAC imbalance: {diff:.1f}°F difference ({coldest} ↔ {warmest})",
                    data={"differential_f": diff, "coldest": coldest, "warmest": warmest},
                ))

        return alerts
