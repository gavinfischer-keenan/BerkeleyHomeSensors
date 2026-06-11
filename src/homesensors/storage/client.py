"""InfluxDB client singleton — thread-safe, lazy-initialised."""

from __future__ import annotations

import threading

import structlog
from influxdb_client import InfluxDBClient

from homesensors.config import settings

log = structlog.get_logger(__name__)

_client: InfluxDBClient | None = None
_lock = threading.Lock()


def get_influx_client() -> InfluxDBClient:
    """Return (or create) the global InfluxDB client."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = InfluxDBClient(
                    url=settings.influxdb_url,
                    token=settings.influxdb_token,
                    org=settings.influxdb_org,
                )
                log.info("influx_client.created", url=settings.influxdb_url)
    return _client


def close_influx_client() -> None:
    """Cleanly close the global client (call on shutdown)."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None
            log.info("influx_client.closed")
