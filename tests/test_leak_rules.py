"""Tests for leak detection rules — the most critical rules in the system."""
from homesensors.ingest.schema import LeakReading
from homesensors.rules.leak_rules import LeakRules


def test_wet_sensor_triggers_critical_alert():
    rules = LeakRules()
    reading = LeakReading(sensor_id="kitchen-sink", location="Kitchen Sink", wet=True)
    alerts = rules.evaluate(reading)
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert "WATER LEAK" in alerts[0].title


def test_dry_sensor_no_alert():
    rules = LeakRules()
    reading = LeakReading(sensor_id="kitchen-sink", location="Kitchen Sink", wet=False)
    alerts = rules.evaluate(reading)
    assert len(alerts) == 0


def test_flow_spike_triggers_warning():
    rules = LeakRules()
    reading = LeakReading(
        sensor_id="main-supply", location="Main Supply",
        wet=False, flow_gpm=15.0, pressure_psi=50.0,
    )
    alerts = rules.evaluate(reading)
    # flow_gpm > 10 should trigger a warning
    flow_alerts = [a for a in alerts if "flow" in a.title.lower() or "flow" in a.message.lower()]
    assert len(flow_alerts) >= 1 or reading.flow_gpm <= 10.0


def test_pressure_drop_triggers_warning():
    rules = LeakRules()
    reading = LeakReading(
        sensor_id="main-supply", location="Main Supply",
        wet=False, flow_gpm=1.0, pressure_psi=15.0,
    )
    alerts = rules.evaluate(reading)
    pressure_alerts = [a for a in alerts if "pressure" in a.title.lower() or "pressure" in a.message.lower()]
    assert len(pressure_alerts) >= 1 or (reading.pressure_psi or 50) >= 25
