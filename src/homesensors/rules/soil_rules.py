"""Soil moisture rules — dry zones, over-watering, fire-season pre-hydration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from homesensors.config import settings
from homesensors.rules.engine import Alert

log = structlog.get_logger(__name__)

# Fire season in Berkeley Hills: roughly June–November
_FIRE_SEASON_MONTHS = {6, 7, 8, 9, 10, 11}


class SoilRules:
    """Evaluate soil moisture readings."""

    def __init__(self) -> None:
        # Track latest moisture per zone for cross-zone fire-season check
        self._zone_moisture: dict[str, float] = {}

    def evaluate(self, reading: Any) -> list[Alert]:
        alerts: list[Alert] = []
        zone = reading.zone_id
        moisture = reading.moisture_pct
        self._zone_moisture[zone] = moisture

        # ── Dry zone (<20%) ────────────────────────────────────────────
        if moisture < settings.soil_dry_pct:
            alerts.append(Alert(
                severity="INFO",
                source="soil_rules",
                sensor_type="soil",
                sensor_id=zone,
                message=f"Dry zone {zone}: {moisture:.1f}% moisture",
                data={"moisture_pct": moisture, "zone_id": zone},
            ))

        # ── Over-watering (>80%) ──────────────────────────────────────
        if moisture > settings.soil_over_water_pct:
            alerts.append(Alert(
                severity="WARNING",
                source="soil_rules",
                sensor_type="soil",
                sensor_id=zone,
                message=f"Over-watering zone {zone}: {moisture:.1f}% moisture",
                data={"moisture_pct": moisture, "zone_id": zone},
            ))

        # ── Fire season pre-hydration alert ───────────────────────────
        now = datetime.now()
        if now.month in _FIRE_SEASON_MONTHS and len(self._zone_moisture) >= 2:
            if all(m < settings.soil_fire_season_pct for m in self._zone_moisture.values()):
                alerts.append(Alert(
                    severity="WARNING",
                    source="soil_rules",
                    sensor_type="soil",
                    sensor_id="all-zones",
                    message=f"FIRE SEASON: All {len(self._zone_moisture)} zones below {settings.soil_fire_season_pct}% — trigger pre-hydration",
                    data={"zones": dict(self._zone_moisture)},
                ))

        return alerts
