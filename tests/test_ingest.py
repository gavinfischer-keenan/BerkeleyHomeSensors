"""Tests for Pydantic ingest schemas."""
from homesensors.ingest.schema import SoilReading, LeakReading, PowerReading, ClimateReading


def test_soil_reading_valid():
    r = SoilReading(zone_id="zone-front-lawn", moisture_pct=45.2, raw_mv=1200, soil_temp_c=18.5)
    assert r.moisture_pct == 45.2
    point = r.to_influx_point()
    assert point["measurement"] == "soil_moisture"
    assert point["tags"]["zone_id"] == "zone-front-lawn"


def test_leak_reading_wet():
    r = LeakReading(sensor_id="kitchen-sink", location="Kitchen Sink", wet=True, flow_gpm=0.5)
    assert r.wet is True
    point = r.to_influx_point()
    assert point["fields"]["wet"] is True


def test_leak_reading_dry():
    r = LeakReading(sensor_id="bathroom-1", location="Bathroom 1", wet=False)
    assert r.wet is False


def test_power_reading():
    r = PowerReading(circuit_id="main", watts=4500.0, voltage=120.3, amps=37.4, kwh_today=52.1)
    point = r.to_influx_point()
    assert point["measurement"] == "power"
    assert point["fields"]["watts"] == 4500.0


def test_climate_reading():
    r = ClimateReading(room_id="living-room", temp_f=72.5, humidity_pct=48.0)
    point = r.to_influx_point()
    assert point["measurement"] == "room_climate"
    assert point["fields"]["temp_f"] == 72.5
