"""FastAPI server — house sensor REST endpoints."""

from __future__ import annotations

from fastapi import FastAPI, Query

from homesensors.storage import queries

app = FastAPI(
    title="Berkeley Home Sensors API",
    version="0.1.0",
    description="REST API for house infrastructure sensor data",
)


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Service health check."""
    return {"status": "ok", "service": "home-sensors"}


# ── Soil ────────────────────────────────────────────────────────────────

@app.get("/api/house/soil")
async def soil_all():
    """Current moisture for all soil zones."""
    data = queries.get_soil_moisture_map()
    return {"sensor_type": "soil", "zones": data}


@app.get("/api/house/soil/{zone_id}/history")
async def soil_history(zone_id: str, hours: int = Query(24, ge=1, le=720)):
    """Historical moisture data for a specific zone."""
    data = queries.get_history("soil", zone_id, hours)
    return {"sensor_type": "soil", "zone_id": zone_id, "hours": hours, "readings": data}


# ── Leak ────────────────────────────────────────────────────────────────

@app.get("/api/house/leaks")
async def leaks(hours: int = Query(24, ge=1, le=720)):
    """Recent leak detection events."""
    data = queries.get_leak_events(hours)
    return {"sensor_type": "leak", "hours": hours, "events": data}


# ── Power ───────────────────────────────────────────────────────────────

@app.get("/api/house/power")
async def power_current():
    """Current power usage across all circuits."""
    # Latest reading per circuit
    data = queries.get_latest("power", "*")
    return {"sensor_type": "power", "circuits": data}


@app.get("/api/house/power/summary")
async def power_summary(days: int = Query(7, ge=1, le=90)):
    """Daily kWh summary by circuit."""
    data = queries.get_daily_power_summary(days)
    return {"sensor_type": "power", "days": days, "summary": data}


# ── Climate ─────────────────────────────────────────────────────────────

@app.get("/api/house/climate")
async def climate_all():
    """Current temperature and humidity for all rooms."""
    data = queries.get_room_temperatures()
    return {"sensor_type": "climate", "rooms": data}


# ── Rachio ──────────────────────────────────────────────────────────────

@app.get("/api/house/rachio")
async def rachio_activity(hours: int = Query(48, ge=1, le=720)):
    """Rachio irrigation activity log."""
    data = queries.get_rachio_activity(hours)
    return {"sensor_type": "rachio", "hours": hours, "activity": data}
