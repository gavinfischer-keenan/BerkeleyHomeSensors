# Berkeley Home Sensors

House infrastructure sensor monitoring service for the Berkeley Home Intelligence Platform.

## Sensor Domains

| Category | Sensors | Alert Priority |
|----------|---------|---------------|
| **Leak Detection** | Water sensors on pipes/fixtures | 🔴 CRITICAL (zero cooldown) |
| **Electricity** | CT clamp monitors (whole-house + circuits) | 🟡 WARNING |
| **Soil Moisture** | Capacitive probes × N garden zones | 🟢 INFO |
| **Room Climate** | Per-room temp + humidity | 🟢 INFO |
| **Rachio** | Irrigation observation (read-only) | — |

## Architecture

```
  ESP32 Soil Probes ─┐
  Zigbee Leak Sensors ┤
  CT Clamp Monitors ──┤──→ MQTT Bus (home/sensors/house/#)
  Room Temp Sensors ──┘            │
                                   ▼
                     BerkeleyHomeSensors (this service)
                     ├── Ingest → Pydantic validation
                     ├── Storage → InfluxDB (3-tier retention)
                     ├── Rules → Alerts via MQTT
                     ├── Rachio Observer → poll + record
                     └── API → FastAPI /api/house/*
```

## MQTT Topics

### Inbound (subscribed)
```
home/sensors/house/soil/{zone_id}       ← moisture, raw_mv, soil_temp
home/sensors/house/leak/{sensor_id}     ← wet (bool), flow_gpm, pressure_psi
home/sensors/house/power/{circuit_id}   ← watts, voltage, amps, kwh_today
home/sensors/house/climate/{room_id}    ← temp_f, humidity_pct
```

### Outbound (published)
```
home/alerts/leak                  ← CRITICAL: water detected
home/alerts/power-anomaly         ← overcurrent, voltage sag
home/alerts/soil                  ← dry zones, over-watering
home/alerts/hvac-efficiency       ← comfort drift
home/status/home-sensors          ← agent heartbeat (retained)
home/commands/alexa-say           ← voice alerts
home/commands/display             ← dashboard overrides
```

## Quick Start

```bash
# 1. Install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Configure
cp .env.example .env
nano .env

# 3. Setup InfluxDB buckets
./scripts/setup_influxdb.sh

# 4. Run
python -m homesensors
```

## InfluxDB Storage

| Bucket | Retention | Purpose |
|--------|-----------|---------|
| `house-raw` | 30 days | Full-resolution sensor readings |
| `house-hourly` | 1 year | Downsampled hourly aggregates |
| `house-daily` | Forever | Daily summaries for long-term ML |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/api/house/soil` | All soil zones current moisture |
| GET | `/api/house/soil/{zone_id}/history?hours=24` | Zone history |
| GET | `/api/house/leaks` | Recent leak events |
| GET | `/api/house/power` | Current power usage by circuit |
| GET | `/api/house/power/summary?days=7` | Daily kWh summary |
| GET | `/api/house/climate` | All room temperatures |
| GET | `/api/house/rachio` | Rachio activity log |

## Leak Rules — Priority #1

⚠️ **Leak detection has ZERO cooldown.** Every `wet=True` reading immediately:
1. Publishes `home/alerts/leak` (QoS 1, retained)
2. Sends Alexa voice announcement
3. Sends full-screen dashboard alert
4. (Future) Triggers automated water main shutoff
