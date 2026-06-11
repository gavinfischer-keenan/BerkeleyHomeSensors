"""Batched InfluxDB writer for house sensor readings."""

from __future__ import annotations

import threading
import time
from typing import Any

import structlog
from influxdb_client import Point

from homesensors.config import settings
from homesensors.storage.client import get_influx_client

log = structlog.get_logger(__name__)

_BATCH_SIZE = 50
_FLUSH_INTERVAL_SEC = 1.0


class InfluxWriter:
    """Accumulates reading dicts and flushes to InfluxDB in batches."""

    def __init__(self) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._flush_thread: threading.Thread | None = None

    # ── public API ──────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="influx-flush")
        self._flush_thread.start()
        log.info("influx_writer.started")

    def stop(self) -> None:
        self._running = False
        self._flush_now()  # drain remaining
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5)
        log.info("influx_writer.stopped")

    def write(self, sensor_type: str, reading: Any) -> None:
        """Accept a reading (any schema model) and buffer it."""
        point_dict = reading.to_influx_point()
        with self._lock:
            self._buffer.append(point_dict)
            if len(self._buffer) >= _BATCH_SIZE:
                self._flush_now()

    # ── handler interface (plugs into MQTTSubscriber) ───────────────────

    def handle(self, sensor_type: str, reading: Any) -> None:
        """ReadingHandler compatible callback."""
        self.write(sensor_type, reading)

    # ── internals ───────────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(_FLUSH_INTERVAL_SEC)
            self._flush_now()

    def _flush_now(self) -> None:
        with self._lock:
            batch, self._buffer = self._buffer[:], []

        if not batch:
            return

        try:
            client = get_influx_client()
            write_api = client.write_api()
            points = [self._dict_to_point(d) for d in batch]
            write_api.write(bucket=settings.influxdb_bucket_raw, org=settings.influxdb_org, record=points)
            log.debug("influx_writer.flushed", count=len(points))
        except Exception:
            log.exception("influx_writer.flush_error", lost_points=len(batch))

    @staticmethod
    def _dict_to_point(d: dict) -> Point:
        p = Point(d["measurement"])
        for k, v in d.get("tags", {}).items():
            p.tag(k, v)
        for k, v in d.get("fields", {}).items():
            p.field(k, v)
        p.time(d["time"])
        return p
