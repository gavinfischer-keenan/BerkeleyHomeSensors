"""Leak detection rules — CRITICAL priority, zero cooldown."""

from __future__ import annotations

from typing import Any

import structlog

from homesensors.rules.engine import Alert

log = structlog.get_logger(__name__)

# Thresholds
_FLOW_SPIKE_GPM = 5.0       # unexpected high flow
_PRESSURE_DROP_PSI = 30.0    # below this → possible burst


class LeakRules:
    """Evaluate leak sensor readings.

    All wet==True alerts are CRITICAL with zero cooldown.
    Flow spikes and pressure drops are WARNING.
    """

    def evaluate(self, reading: Any) -> list[Alert]:
        alerts: list[Alert] = []

        # ── wet == True → immediate CRITICAL ───────────────────────────
        if reading.wet:
            alerts.append(Alert(
                severity="CRITICAL",
                source="leak_rules",
                sensor_type="leak",
                sensor_id=reading.sensor_id,
                message=f"WATER DETECTED at {reading.location}",
                data={"location": reading.location, "wet": True},
                cooldown_sec=0,
            ))

        # ── flow rate spike ────────────────────────────────────────────
        if reading.flow_gpm is not None and reading.flow_gpm > _FLOW_SPIKE_GPM:
            alerts.append(Alert(
                severity="WARNING",
                source="leak_rules",
                sensor_type="leak",
                sensor_id=reading.sensor_id,
                message=f"High flow rate {reading.flow_gpm:.1f} GPM at {reading.location}",
                data={"flow_gpm": reading.flow_gpm, "location": reading.location},
                cooldown_sec=0,  # leak-related → zero cooldown
            ))

        # ── pressure drop (possible pipe burst) ───────────────────────
        if reading.pressure_psi is not None and reading.pressure_psi < _PRESSURE_DROP_PSI:
            alerts.append(Alert(
                severity="WARNING",
                source="leak_rules",
                sensor_type="leak",
                sensor_id=reading.sensor_id,
                message=f"Low pressure {reading.pressure_psi:.1f} PSI at {reading.location} — possible pipe burst",
                data={"pressure_psi": reading.pressure_psi, "location": reading.location},
                cooldown_sec=0,  # leak-related → zero cooldown
            ))

        return alerts
