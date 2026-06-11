"""InfluxDB bucket creation and downsampling tasks for house-sensors."""

from __future__ import annotations

import structlog
from influxdb_client import BucketRetentionRules
from influxdb_client.client.tasks_api import TasksApi

from homesensors.config import settings
from homesensors.storage.client import get_influx_client

log = structlog.get_logger(__name__)

# Retention periods in seconds (0 = infinite)
BUCKETS = {
    "house-raw": 30 * 86400,       # 30 days
    "house-hourly": 365 * 86400,   # 1 year
    "house-daily": 0,              # forever
}

DOWNSAMPLING_TASKS = [
    {
        "name": "house-hourly-downsample",
        "every": "1h",
        "offset": "5m",
        "flux": f"""
option task = {{name: "house-hourly-downsample", every: 1h, offset: 5m}}

from(bucket: "{settings.influxdb_bucket_raw}")
  |> range(start: -task.every)
  |> filter(fn: (r) => r._measurement =~ /soil|leak|power|climate|rachio/)
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> to(bucket: "{settings.influxdb_bucket_hourly}", org: "{settings.influxdb_org}")
""",
    },
    {
        "name": "house-daily-downsample",
        "every": "1d",
        "offset": "30m",
        "flux": f"""
option task = {{name: "house-daily-downsample", every: 1d, offset: 30m}}

from(bucket: "{settings.influxdb_bucket_hourly}")
  |> range(start: -task.every)
  |> filter(fn: (r) => r._measurement =~ /soil|leak|power|climate|rachio/)
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> to(bucket: "{settings.influxdb_bucket_daily}", org: "{settings.influxdb_org}")
""",
    },
]


def ensure_buckets() -> None:
    """Create the retention-policy buckets if they don't already exist."""
    client = get_influx_client()
    buckets_api = client.buckets_api()
    existing = {b.name for b in (buckets_api.find_buckets().buckets or [])}

    for name, retention_sec in BUCKETS.items():
        if name in existing:
            log.info("retention.bucket_exists", bucket=name)
            continue
        rules = [BucketRetentionRules(type="expire", every_seconds=retention_sec)] if retention_sec else []
        buckets_api.create_bucket(
            bucket_name=name,
            retention_rules=rules,
            org=settings.influxdb_org,
        )
        log.info("retention.bucket_created", bucket=name, retention_days=retention_sec // 86400 if retention_sec else "infinite")


def ensure_downsampling_tasks() -> None:
    """Create or update Flux downsampling tasks."""
    client = get_influx_client()
    tasks_api: TasksApi = client.tasks_api()

    for task_def in DOWNSAMPLING_TASKS:
        existing = tasks_api.find_tasks(name=task_def["name"])
        if existing:
            log.info("retention.task_exists", task=task_def["name"])
            continue
        tasks_api.create_task_every(
            name=task_def["name"],
            flux=task_def["flux"],
            every=task_def["every"],
            organization=settings.influxdb_org,
        )
        log.info("retention.task_created", task=task_def["name"])


def setup_retention() -> None:
    """One-shot: ensure buckets + downsampling tasks exist."""
    ensure_buckets()
    ensure_downsampling_tasks()
    log.info("retention.setup_complete")
