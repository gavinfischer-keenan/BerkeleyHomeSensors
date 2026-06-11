"""Pydantic v2 models for every sensor type ingested by Home Sensors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Soil ────────────────────────────────────────────────────────────────

class SoilReading(BaseModel):
    """Capacitive or resistive soil-moisture probe reading."""

    zone_id: str = Field(..., description="Irrigation zone identifier, e.g. 'front-lawn'")
    moisture_pct: float = Field(..., ge=0, le=100, description="Volumetric water content %")
    raw_mv: float = Field(..., description="Raw millivolt reading from sensor")
    soil_temp_c: float = Field(..., description="Soil temperature in °C")
    timestamp: datetime = Field(default_factory=_now_utc)

    def to_influx_point(self) -> dict:
        return {
            "measurement": "soil",
            "tags": {"zone_id": self.zone_id},
            "fields": {
                "moisture_pct": self.moisture_pct,
                "raw_mv": self.raw_mv,
                "soil_temp_c": self.soil_temp_c,
            },
            "time": self.timestamp.isoformat(),
        }


# ── Leak ────────────────────────────────────────────────────────────────

class LeakReading(BaseModel):
    """Rope / point leak sensor or inline flow sensor reading."""

    sensor_id: str = Field(..., description="Unique sensor identifier")
    location: str = Field(..., description="Human-readable location, e.g. 'laundry-room'")
    wet: bool = Field(..., description="True when moisture detected")
    flow_gpm: Optional[float] = Field(None, ge=0, description="Gallons per minute if flow sensor")
    pressure_psi: Optional[float] = Field(None, ge=0, description="Line pressure PSI")
    timestamp: datetime = Field(default_factory=_now_utc)

    def to_influx_point(self) -> dict:
        fields: dict = {"wet": self.wet}
        if self.flow_gpm is not None:
            fields["flow_gpm"] = self.flow_gpm
        if self.pressure_psi is not None:
            fields["pressure_psi"] = self.pressure_psi
        return {
            "measurement": "leak",
            "tags": {"sensor_id": self.sensor_id, "location": self.location},
            "fields": fields,
            "time": self.timestamp.isoformat(),
        }


# ── Power ───────────────────────────────────────────────────────────────

class PowerReading(BaseModel):
    """Per-circuit power monitoring (CT clamp or smart breaker)."""

    circuit_id: str = Field(..., description="Circuit label, e.g. 'kitchen-20A'")
    watts: float = Field(..., description="Instantaneous wattage")
    voltage: float = Field(..., description="Line voltage")
    amps: float = Field(..., ge=0, description="Current draw in amps")
    kwh_today: float = Field(..., ge=0, description="Cumulative kWh since midnight")
    timestamp: datetime = Field(default_factory=_now_utc)

    def to_influx_point(self) -> dict:
        return {
            "measurement": "power",
            "tags": {"circuit_id": self.circuit_id},
            "fields": {
                "watts": self.watts,
                "voltage": self.voltage,
                "amps": self.amps,
                "kwh_today": self.kwh_today,
            },
            "time": self.timestamp.isoformat(),
        }


# ── Climate ─────────────────────────────────────────────────────────────

class ClimateReading(BaseModel):
    """Indoor temperature / humidity / pressure sensor."""

    room_id: str = Field(..., description="Room identifier, e.g. 'master-bedroom'")
    temp_f: float = Field(..., description="Temperature in °F")
    humidity_pct: float = Field(..., ge=0, le=100, description="Relative humidity %")
    pressure_hpa: Optional[float] = Field(None, description="Barometric pressure hPa")
    timestamp: datetime = Field(default_factory=_now_utc)

    def to_influx_point(self) -> dict:
        fields: dict = {
            "temp_f": self.temp_f,
            "humidity_pct": self.humidity_pct,
        }
        if self.pressure_hpa is not None:
            fields["pressure_hpa"] = self.pressure_hpa
        return {
            "measurement": "climate",
            "tags": {"room_id": self.room_id},
            "fields": fields,
            "time": self.timestamp.isoformat(),
        }


# ── Rachio Activity ────────────────────────────────────────────────────

class RachioActivity(BaseModel):
    """Observed irrigation run from Rachio API."""

    zone_id: str = Field(..., description="Rachio zone ID")
    zone_name: str = Field(..., description="Human-readable zone name")
    duration_min: float = Field(..., ge=0, description="Run duration in minutes")
    schedule_type: str = Field(..., description="'manual', 'fixed', 'flex_daily', etc.")
    rain_delay: bool = Field(False, description="True if a rain delay is active")
    timestamp: datetime = Field(default_factory=_now_utc)

    def to_influx_point(self) -> dict:
        return {
            "measurement": "rachio",
            "tags": {
                "zone_id": self.zone_id,
                "zone_name": self.zone_name,
                "schedule_type": self.schedule_type,
            },
            "fields": {
                "duration_min": self.duration_min,
                "rain_delay": self.rain_delay,
            },
            "time": self.timestamp.isoformat(),
        }


# Convenience mapping for topic → model class
SENSOR_TYPE_MAP: dict[str, type[BaseModel]] = {
    "soil": SoilReading,
    "leak": LeakReading,
    "power": PowerReading,
    "climate": ClimateReading,
}
