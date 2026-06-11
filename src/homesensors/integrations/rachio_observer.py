"""Rachio observer — polls the Rachio API for irrigation activity (read-only)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import structlog

from homesensors.config import settings
from homesensors.ingest.schema import RachioActivity

log = structlog.get_logger(__name__)

_BASE_URL = "https://api.rach.io/1"


class RachioObserver:
    """Observe Rachio irrigation runs without issuing commands.

    Polls every ``rachio_poll_interval_sec`` (default 5 min):
      1. GET /public/person/info → discover devices
      2. GET /public/device/{id}/current_schedule → running zones
      3. Record to InfluxDB via the provided writer callback.
    """

    def __init__(self, write_callback=None) -> None:
        self._api_key = settings.rachio_api_key
        self._device_id = settings.rachio_device_id
        self._poll_sec = settings.rachio_poll_interval_sec
        self._write_callback = write_callback
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ── lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.enabled:
            log.info("rachio_observer.disabled", reason="no API key")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info("rachio_observer.started", poll_sec=self._poll_sec)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("rachio_observer.stopped")

    # ── polling ─────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception:
                log.exception("rachio_observer.poll_error")
            await asyncio.sleep(self._poll_sec)

    async def _poll_once(self) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            # If no device_id configured, discover it
            device_id = self._device_id
            if not device_id:
                device_id = await self._discover_device(client)
                if not device_id:
                    return

            # Current schedule
            resp = await client.get(
                f"{_BASE_URL}/public/device/{device_id}/current_schedule",
                headers=self._headers(),
            )
            resp.raise_for_status()
            schedule = resp.json()

            if not schedule or schedule.get("status") == "NOT_WATERING":
                log.debug("rachio_observer.not_watering")
                return

            # Check for rain delay
            rain_delay = await self._check_rain_delay(client, device_id)

            # Record each running zone
            for zone_run in schedule.get("zones", [schedule] if "zoneId" in schedule else []):
                activity = RachioActivity(
                    zone_id=zone_run.get("zoneId", "unknown"),
                    zone_name=zone_run.get("zoneName", zone_run.get("name", "unknown")),
                    duration_min=zone_run.get("duration", 0) / 60.0,
                    schedule_type=schedule.get("type", "unknown"),
                    rain_delay=rain_delay,
                    timestamp=datetime.now(timezone.utc),
                )
                log.info("rachio_observer.zone_running", zone=activity.zone_name, duration=activity.duration_min)
                if self._write_callback:
                    self._write_callback("rachio", activity)

    async def _discover_device(self, client: httpx.AsyncClient) -> str | None:
        resp = await client.get(
            f"{_BASE_URL}/public/person/info",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        devices = data.get("devices", [])
        if not devices:
            log.warning("rachio_observer.no_devices")
            return None
        device_id = devices[0].get("id", "")
        log.info("rachio_observer.discovered_device", device_id=device_id)
        return device_id

    async def _check_rain_delay(self, client: httpx.AsyncClient, device_id: str) -> bool:
        try:
            resp = await client.get(
                f"{_BASE_URL}/public/device/{device_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("rainDelayExpirationDate"))
        except Exception:
            return False
