"""Main entry point — wires up MQTT, InfluxDB, rules, Rachio, API, and health."""

from __future__ import annotations

import asyncio
import signal
import sys
import threading

import structlog
import uvicorn

from homesensors.config import settings


def _configure_logging() -> None:
    """Set up structlog with the configured log level."""
    import logging

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


log: structlog.BoundLogger = structlog.get_logger(__name__)


async def _run() -> None:
    """Async main — start all subsystems."""
    from homesensors.ingest.influx_writer import InfluxWriter
    from homesensors.ingest.mqtt_subscriber import MQTTSubscriber
    from homesensors.integrations.dashboard import DashboardForwarder
    from homesensors.integrations.mqtt_publisher import MQTTPublisher
    from homesensors.integrations.rachio_observer import RachioObserver
    from homesensors.rules.engine import RulesEngine
    from homesensors.storage.retention import setup_retention
    from homesensors.telemetry.health import HealthMonitor

    # ── InfluxDB setup ──────────────────────────────────────────────────
    try:
        setup_retention()
    except Exception:
        log.warning("main.retention_setup_failed", exc_info=True)

    # ── Instantiate components ──────────────────────────────────────────
    publisher = MQTTPublisher()
    influx_writer = InfluxWriter()
    rules_engine = RulesEngine()
    rules_engine.set_publisher(publisher)
    dashboard = DashboardForwarder()
    health = HealthMonitor()
    health.set_publisher(publisher)
    rachio = RachioObserver(write_callback=influx_writer.handle)

    subscriber = MQTTSubscriber(handlers=[
        influx_writer.handle,
        rules_engine.handle,
        dashboard.forward,
    ])

    # ── Start everything ────────────────────────────────────────────────
    publisher.start()
    influx_writer.start()
    dashboard.start()
    subscriber.start()
    health.set_mqtt_status(True)

    await rachio.start()
    await health.start()

    log.info("main.started", api_port=settings.api_port)

    # ── Start FastAPI in a background thread ────────────────────────────
    from homesensors.api.server import app

    api_config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
    api_server = uvicorn.Server(api_config)
    api_thread = threading.Thread(target=api_server.run, daemon=True, name="api-server")
    api_thread.start()

    # ── Wait for shutdown signal ────────────────────────────────────────
    stop_event = asyncio.Event()

    def _signal_handler(sig: int, frame) -> None:
        log.info("main.signal_received", signal=sig)
        stop_event.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    await stop_event.wait()

    # ── Graceful shutdown ───────────────────────────────────────────────
    log.info("main.shutting_down")
    await health.stop()
    await rachio.stop()
    subscriber.stop()
    dashboard.stop()
    influx_writer.stop()
    publisher.stop()  # publishes offline status (retained)

    from homesensors.storage.client import close_influx_client
    close_influx_client()

    log.info("main.stopped")


def main() -> None:
    """Synchronous entry point for ``pyproject.toml`` script."""
    _configure_logging()
    log.info("main.starting", version="0.1.0")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("main.interrupted")
    sys.exit(0)


if __name__ == "__main__":
    main()
