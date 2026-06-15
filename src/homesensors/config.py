"""Centralised configuration via pydantic-settings + .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables for the Home Sensors service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── MQTT ────────────────────────────────────────────────────────────
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_client_id: str = "berkeley-homesensors"
    mqtt_topic_root: str = "home/sensors/house"
    mqtt_status_topic: str = "home/status/home-sensors"

    # ── InfluxDB ────────────────────────────────────────────────────────
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "your-token-here"
    influxdb_org: str = "berkeley"
    influxdb_bucket_raw: str = "house-raw"
    influxdb_bucket_hourly: str = "house-hourly"
    influxdb_bucket_daily: str = "house-daily"

    # ── Rachio (observation only) ───────────────────────────────────────
    rachio_api_key: str = ""
    rachio_device_id: str = ""
    rachio_poll_interval_sec: int = 300  # 5 minutes

    # ── Dashboard ───────────────────────────────────────────────────────
    dashboard_url: str = "http://localhost:5050/api/ingest/home-sensors"

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── API ─────────────────────────────────────────────────────────────
    api_port: int = 8082
    api_host: str = "0.0.0.0"

    # ── Rules ───────────────────────────────────────────────────────────
    alert_cooldown_sec: int = 300
    comfort_temp_min_f: float = 65.0
    comfort_temp_max_f: float = 78.0
    humidity_mold_threshold: float = 65.0
    soil_dry_pct: float = 20.0
    soil_over_water_pct: float = 80.0
    soil_fire_season_pct: float = 15.0
    power_overcurrent_watts: float = 3600.0
    voltage_min: float = 110.0
    voltage_max: float = 130.0
    breaker_trip_zero_watts_threshold: float = 5.0  # below this = "off/tripped"
    breaker_trip_min_prior_watts: float = 100.0     # must have been drawing this to count
    breaker_trip_window: int = 5                    # consecutive zero readings before alert

    # ── Circuit Labels ──────────────────────────────────────────────────
    circuit_labels_path: Path = Path("./circuit_labels.yml")

    # ── Health ──────────────────────────────────────────────────────────
    heartbeat_interval_sec: int = 30


# Module-level singleton — import and use directly.
settings = Settings()
