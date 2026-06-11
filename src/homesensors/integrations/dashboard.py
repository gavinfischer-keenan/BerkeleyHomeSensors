"""Dashboard HTTP forwarder — POST sensor summaries to the central dashboard."""

from __future__ import annotations

import threading
from typing import Any

import httpx
import structlog

from homesensors.config import settings

log = structlog.get_logger(__name__)


class DashboardForwarder:
    """Forward digested readings to the central dashboard API.

    Uses a background thread with httpx to avoid blocking the ingest path.
    """

    def __init__(self) -> None:
        self._url = settings.dashboard_url
        self._client: httpx.Client | None = None

    def start(self) -> None:
        self._client = httpx.Client(timeout=10)
        log.info("dashboard.started", url=self._url)

    def stop(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
        log.info("dashboard.stopped")

    def forward(self, sensor_type: str, reading: Any) -> None:
        """ReadingHandler compatible — fire-and-forget POST."""
        if not self._client:
            return
        threading.Thread(
            target=self._post,
            args=(sensor_type, reading),
            daemon=True,
        ).start()

    def _post(self, sensor_type: str, reading: Any) -> None:
        try:
            payload = {
                "sensor_type": sensor_type,
                "reading": reading.model_dump(mode="json"),
            }
            resp = self._client.post(self._url, json=payload)  # type: ignore[union-attr]
            if resp.status_code >= 400:
                log.warning("dashboard.post_failed", status=resp.status_code, body=resp.text[:200])
            else:
                log.debug("dashboard.posted", sensor_type=sensor_type)
        except Exception:
            log.exception("dashboard.post_error")
