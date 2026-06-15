"""MQTT publisher — agent lifecycle, alerts, and external commands."""

from __future__ import annotations

import json
from typing import Any

import paho.mqtt.client as mqtt
import structlog

from homesensors.config import settings

log = structlog.get_logger(__name__)


class MQTTPublisher:
    """Publish alerts, status, and commands over MQTT.

    Lifecycle
    ---------
    * ``start()`` → publishes *online* (retained) to status topic.
    * ``stop()``  → publishes *offline* (retained) to status topic.
    * LWT ensures *offline* on unexpected disconnect.
    """

    def __init__(self) -> None:
        self._client = mqtt.Client(
            client_id=f"{settings.mqtt_client_id}-pub",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        # LWT: mark offline on ungraceful disconnect
        self._client.will_set(
            settings.mqtt_status_topic,
            payload=json.dumps({"status": "offline", "service": "home-sensors"}),
            qos=1,
            retain=True,
        )

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._client.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=60)
        self._client.loop_start()
        self._publish_status("online")
        log.info("mqtt_publisher.started")

    def stop(self) -> None:
        self._publish_status("offline")
        self._client.loop_stop()
        self._client.disconnect()
        log.info("mqtt_publisher.stopped")

    # ── alert publishing ────────────────────────────────────────────────

    def publish_alert(self, topic: str, alert: Any) -> None:
        """Publish a generic alert to the given topic."""
        payload = self._alert_to_payload(alert)
        self._client.publish(topic, json.dumps(payload), qos=1, retain=False)
        log.info("mqtt_publisher.alert", topic=topic, severity=payload.get("severity"))

    def alert_leak(self, alert: Any) -> None:
        """Publish a leak alert — QoS 1, retained."""
        payload = self._alert_to_payload(alert)
        topic = f"home/alerts/leak/{alert.sensor_id}"
        self._client.publish(topic, json.dumps(payload), qos=1, retain=True)
        log.warning("mqtt_publisher.leak_alert", topic=topic, message=alert.message)

    def alert_power(self, alert: Any) -> None:
        """Publish a power alert."""
        payload = self._alert_to_payload(alert)
        topic = f"home/alerts/power/{alert.sensor_id}"
        self._client.publish(topic, json.dumps(payload), qos=1, retain=False)
        log.info("mqtt_publisher.power_alert", topic=topic, message=alert.message)

    def alert_breaker(self, alert: Any) -> None:
        """Publish a breaker-trip alert — QoS 1, retained so BerkeleyAlarms sees it on connect."""
        payload = self._alert_to_payload(alert)
        topic = f"home/alerts/breaker/{alert.sensor_id}"
        # Retained so the alarm service catches it even if it restarts shortly after
        self._client.publish(topic, json.dumps(payload), qos=1, retain=True)
        log.warning("mqtt_publisher.breaker_trip", topic=topic, circuit=alert.sensor_id)

    # ── external commands ───────────────────────────────────────────────

    def command_alexa_say(self, text: str) -> None:
        """Ask Alexa to make a voice announcement."""
        payload = {"command": "say", "text": text}
        self._client.publish("home/commands/alexa/say", json.dumps(payload), qos=1)
        log.info("mqtt_publisher.alexa_say", text=text[:80])

    def command_display(self, command: str, data: dict) -> None:
        """Send a command to the home display."""
        payload = {"command": command, **data}
        self._client.publish("home/commands/display", json.dumps(payload), qos=1)
        log.info("mqtt_publisher.display_command", command=command)

    # ── internals ───────────────────────────────────────────────────────

    def _publish_status(self, status: str) -> None:
        payload = {"status": status, "service": "home-sensors"}
        self._client.publish(
            settings.mqtt_status_topic,
            json.dumps(payload),
            qos=1,
            retain=True,
        )
        log.info("mqtt_publisher.status", status=status)

    @staticmethod
    def _alert_to_payload(alert: Any) -> dict:
        return {
            "severity": alert.severity,
            "source": alert.source,
            "sensor_type": alert.sensor_type,
            "sensor_id": alert.sensor_id,
            "message": alert.message,
            "data": alert.data,
        }
