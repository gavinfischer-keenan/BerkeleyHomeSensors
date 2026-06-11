"""MQTT subscriber — listens to home/sensors/house/# and dispatches readings."""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Callable

import paho.mqtt.client as mqtt
import structlog

from homesensors.config import settings
from homesensors.ingest.schema import SENSOR_TYPE_MAP

if TYPE_CHECKING:
    from paho.mqtt.client import Client, MQTTMessage

log = structlog.get_logger(__name__)

# Type alias for handler callbacks
ReadingHandler = Callable[[str, object], None]


class MQTTSubscriber:
    """Subscribe to home/sensors/house/# and parse incoming sensor payloads."""

    def __init__(self, handlers: list[ReadingHandler] | None = None) -> None:
        self._handlers: list[ReadingHandler] = handlers or []
        self._client = mqtt.Client(
            client_id=settings.mqtt_client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        # Last Will & Testament — marks service offline on unexpected disconnect
        self._client.will_set(
            settings.mqtt_status_topic,
            payload=json.dumps({"status": "offline", "service": "home-sensors"}),
            qos=1,
            retain=True,
        )
        self._thread: threading.Thread | None = None

    # ── public API ──────────────────────────────────────────────────────

    def add_handler(self, handler: ReadingHandler) -> None:
        self._handlers.append(handler)

    def start(self) -> None:
        log.info("mqtt_subscriber.connecting", broker=settings.mqtt_broker, port=settings.mqtt_port)
        self._client.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        log.info("mqtt_subscriber.stopping")
        self._client.loop_stop()
        self._client.disconnect()

    # ── callbacks ───────────────────────────────────────────────────────

    def _on_connect(self, client: Client, userdata: object, flags: dict, rc: int, properties: object = None) -> None:
        topic = f"{settings.mqtt_topic_root}/#"
        client.subscribe(topic, qos=1)
        log.info("mqtt_subscriber.subscribed", topic=topic)

    def _on_disconnect(self, client: Client, userdata: object, flags: dict, rc: int, properties: object = None) -> None:
        log.warning("mqtt_subscriber.disconnected", rc=rc)

    def _on_message(self, client: Client, userdata: object, msg: MQTTMessage) -> None:
        try:
            self._dispatch(msg)
        except Exception:
            log.exception("mqtt_subscriber.dispatch_error", topic=msg.topic)

    # ── dispatch ────────────────────────────────────────────────────────

    def _dispatch(self, msg: MQTTMessage) -> None:
        """Parse topic → sensor type, validate payload, fan-out to handlers."""
        # Topic format: home/sensors/house/<sensor_type>[/<optional_id>]
        parts = msg.topic.split("/")
        if len(parts) < 4:
            log.warning("mqtt_subscriber.bad_topic", topic=msg.topic)
            return

        sensor_type = parts[3]  # soil | leak | power | climate
        model_cls = SENSOR_TYPE_MAP.get(sensor_type)
        if model_cls is None:
            log.warning("mqtt_subscriber.unknown_sensor_type", sensor_type=sensor_type, topic=msg.topic)
            return

        payload = json.loads(msg.payload.decode("utf-8"))
        reading = model_cls.model_validate(payload)
        log.debug("mqtt_subscriber.reading", sensor_type=sensor_type, reading=reading.model_dump())

        for handler in self._handlers:
            try:
                handler(sensor_type, reading)
            except Exception:
                log.exception("mqtt_subscriber.handler_error", handler=handler)
