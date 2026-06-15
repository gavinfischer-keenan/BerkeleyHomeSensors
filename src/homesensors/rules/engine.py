"""Rule engine — evaluates readings against all rule sets and dispatches alerts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from homesensors.config import settings

log = structlog.get_logger(__name__)


@dataclass
class Alert:
    """Represents a rule-engine alert."""
    severity: str          # CRITICAL | WARNING | INFO
    source: str            # e.g. "leak_rules", "power_rules"
    sensor_type: str       # soil | leak | power | climate
    sensor_id: str         # zone_id / sensor_id / circuit_id / room_id
    message: str
    data: dict = field(default_factory=dict)
    cooldown_sec: int = 0  # 0 = no cooldown (always fire)


class RulesEngine:
    """Central rule orchestrator.

    Each incoming reading is evaluated against the matching rule modules.
    Alerts that pass cooldown checks are dispatched to the MQTT publisher.
    """

    def __init__(self) -> None:
        from homesensors.rules.leak_rules import LeakRules
        from homesensors.rules.power_rules import PowerRules
        from homesensors.rules.soil_rules import SoilRules
        from homesensors.rules.climate_rules import ClimateRules

        self._rule_sets: dict[str, list] = {
            "leak": [LeakRules()],
            "power": [PowerRules()],
            "soil": [SoilRules()],
            "climate": [ClimateRules()],
        }
        self._last_alert_time: dict[str, float] = {}
        self._publisher = None  # set via set_publisher()
        self._default_cooldown = settings.alert_cooldown_sec

    def set_publisher(self, publisher: Any) -> None:
        """Inject the MQTT publisher for alert dispatch."""
        self._publisher = publisher

    # ── ReadingHandler interface ────────────────────────────────────────

    def handle(self, sensor_type: str, reading: Any) -> None:
        """Evaluate all rules for this sensor type."""
        rule_list = self._rule_sets.get(sensor_type, [])
        for rule_set in rule_list:
            alerts = rule_set.evaluate(reading)
            for alert in alerts:
                self._dispatch(alert)

    # ── dispatch with cooldown ──────────────────────────────────────────

    def _dispatch(self, alert: Alert) -> None:
        cooldown = alert.cooldown_sec if alert.cooldown_sec > 0 else (
            0 if alert.severity == "CRITICAL" else self._default_cooldown
        )

        key = f"{alert.source}:{alert.sensor_type}:{alert.sensor_id}:{alert.message}"
        now = time.time()

        if cooldown > 0:
            last = self._last_alert_time.get(key, 0)
            if now - last < cooldown:
                log.debug("rules_engine.cooldown_suppressed", key=key)
                return

        self._last_alert_time[key] = now
        log.info(
            "rules_engine.alert",
            severity=alert.severity,
            source=alert.source,
            sensor_id=alert.sensor_id,
            message=alert.message,
        )

        if self._publisher:
            try:
                if alert.sensor_type == "leak":
                    # Publishes to home/alerts/leak/{sensor_id} — BerkeleyAlarms
                    # subscribes and handles Alexa TTS + repeat scheduling.
                    self._publisher.alert_leak(alert)
                elif alert.sensor_type == "power":
                    self._publisher.alert_power(alert)
                elif alert.sensor_type == "breaker":
                    # Breaker trips route to home/alerts/breaker/{circuit_id}
                    # BerkeleyAlarms picks up and announces circuit name via TTS.
                    self._publisher.alert_breaker(alert)
                else:
                    self._publisher.publish_alert(
                        f"home/alerts/{alert.sensor_type}/{alert.sensor_id}",
                        alert,
                    )
                # NOTE: Alexa announcements are now handled centrally by
                # BerkeleyAlarms (subscribes home/alerts/#). Do NOT call
                # command_alexa_say here — it would cause double-announcements.
            except Exception:
                log.exception("rules_engine.publish_error")
