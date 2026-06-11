"""Pre-built Flux queries for the house-sensors buckets."""

from __future__ import annotations

import structlog

from homesensors.config import settings
from homesensors.storage.client import get_influx_client

log = structlog.get_logger(__name__)


def _query(flux: str) -> list[dict]:
    """Execute a Flux query and return results as list of dicts."""
    client = get_influx_client()
    query_api = client.query_api()
    tables = query_api.query(flux, org=settings.influxdb_org)
    results: list[dict] = []
    for table in tables:
        for record in table.records:
            results.append(record.values)
    return results


# ── Generic helpers ─────────────────────────────────────────────────────

def get_latest(sensor_type: str, sensor_id: str) -> list[dict]:
    """Last reading for a specific sensor."""
    tag_key = {
        "soil": "zone_id",
        "leak": "sensor_id",
        "power": "circuit_id",
        "climate": "room_id",
    }.get(sensor_type, "sensor_id")

    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "{sensor_type}")
  |> filter(fn: (r) => r["{tag_key}"] == "{sensor_id}")
  |> last()
"""
    return _query(flux)


def get_history(sensor_type: str, sensor_id: str, hours: int = 24) -> list[dict]:
    """Time-range history for a specific sensor."""
    tag_key = {
        "soil": "zone_id",
        "leak": "sensor_id",
        "power": "circuit_id",
        "climate": "room_id",
    }.get(sensor_type, "sensor_id")

    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "{sensor_type}")
  |> filter(fn: (r) => r["{tag_key}"] == "{sensor_id}")
  |> sort(columns: ["_time"])
"""
    return _query(flux)


# ── Power ───────────────────────────────────────────────────────────────

def get_daily_power_summary(days: int = 7) -> list[dict]:
    """kWh by circuit aggregated daily."""
    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "power" and r._field == "kwh_today")
  |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
  |> group(columns: ["circuit_id"])
  |> sort(columns: ["_time"])
"""
    return _query(flux)


# ── Soil ────────────────────────────────────────────────────────────────

def get_soil_moisture_map() -> list[dict]:
    """Current moisture for every zone (latest reading per zone)."""
    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "soil" and r._field == "moisture_pct")
  |> group(columns: ["zone_id"])
  |> last()
"""
    return _query(flux)


# ── Leak ────────────────────────────────────────────────────────────────

def get_leak_events(hours: int = 24) -> list[dict]:
    """Recent leak detections (wet == true)."""
    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "leak" and r._field == "wet" and r._value == true)
  |> sort(columns: ["_time"], desc: true)
"""
    return _query(flux)


# ── Climate ─────────────────────────────────────────────────────────────

def get_room_temperatures() -> list[dict]:
    """Current temperature for every room."""
    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "climate" and r._field == "temp_f")
  |> group(columns: ["room_id"])
  |> last()
"""
    return _query(flux)


# ── Rachio ──────────────────────────────────────────────────────────────

def get_rachio_activity(hours: int = 48) -> list[dict]:
    """Recent Rachio irrigation runs."""
    flux = f"""
from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "rachio")
  |> sort(columns: ["_time"], desc: true)
"""
    return _query(flux)
