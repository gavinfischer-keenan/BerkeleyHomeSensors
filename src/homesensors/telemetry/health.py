"""Health monitor — checks MQTT, InfluxDB, and sensor last-seen times."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from homesensors.config import settings
from homesensors.storage.client import get_influx_client

log = structlog.get_logger(__name__)

# How long before a sensor is considered stale
_STALE_THRESHOLD_SEC = 600  # 10 minutes


class HealthMonitor:
    """Track component and sensor health, emit periodic heartbeats."""

    def __init__(self) -> None:
        self._last_seen: dict[str, float] = {}  # "sensor_type:sensor_id" -> epoch
        self._mqtt_ok = False
        self._influx_ok = False
        self._running = False
        self._task: asyncio.Task | None = None
        self._publisher: Any = None
        self._start_time: float = 0.0

    def set_publisher(self, publisher: Any) -> None:
        self._publisher = publisher

    # ── tracking ────────────────────────────────────────────────────────

    def mark_seen(self, sensor_type: str, sensor_id: str) -> None:
        """Called on every successful reading to track liveness."""
        self._last_seen[f"{sensor_type}:{sensor_id}"] = time.time()

    def set_mqtt_status(self, ok: bool) -> None:
        self._mqtt_ok = ok

    def set_influx_status(self, ok: bool) -> None:
        self._influx_ok = ok

    # ── health snapshot ─────────────────────────────────────────────────

    def get_status(self) -> dict:
        now = time.time()
        stale_sensors = [
            key for key, ts in self._last_seen.items()
            if now - ts > _STALE_THRESHOLD_SEC
        ]
        return {
            "service": "home-sensors",
            "mqtt_connected": self._mqtt_ok,
            "influx_connected": self._influx_ok,
            "sensors_tracked": len(self._last_seen),
            "stale_sensors": stale_sensors,
            "uptime_sec": int(now - self._start_time) if self._start_time else 0,
        }

    # ── heartbeat loop ──────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._heartbeat_loop())
        log.info("health.started", interval=settings.heartbeat_interval_sec)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("health.stopped")

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                self._check_influx()
                status = self.get_status()
                log.info("health.heartbeat", **status)
                if self._publisher:
                    self._publisher.command_display("health", status)
            except Exception:
                log.exception("health.heartbeat_error")
            await asyncio.sleep(settings.heartbeat_interval_sec)

    def _check_influx(self) -> None:
        try:
            client = get_influx_client()
            health = client.health()
            self._influx_ok = health.status == "pass"
        except Exception:
            self._influx_ok = False
