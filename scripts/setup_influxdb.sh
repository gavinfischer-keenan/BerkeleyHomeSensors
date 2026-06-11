#!/usr/bin/env bash
# Create InfluxDB buckets for house sensor data
set -euo pipefail

INFLUX_URL="${INFLUXDB_URL:-http://localhost:8086}"
INFLUX_TOKEN="${INFLUXDB_TOKEN:?INFLUXDB_TOKEN must be set}"
INFLUX_ORG="${INFLUXDB_ORG:-berkeley}"

echo "Creating InfluxDB buckets for BerkeleyHomeSensors..."

influx bucket create --name house-raw    --retention 30d  --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  house-raw already exists"
influx bucket create --name house-hourly --retention 365d --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  house-hourly already exists"
influx bucket create --name house-daily  --retention 0    --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  house-daily already exists"

echo "Done. Buckets: house-raw (30d), house-hourly (1y), house-daily (forever)"
