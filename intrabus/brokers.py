"""ZeroMQ broker helpers used by intrabus.

`TopicBroker`  – a PUB/SUB forwarder (aka "XSUB↔XPUB" pattern).
`CentralBroker` – a ROUTER‑based request/reply router.
Both can be started programmatically or via helper runners.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import zmq

from .config import (
    FORWARDER_PUB_ADDR,
    FORWARDER_SUB_ADDR,
    INTRABUS_NODE_MODULE,
    REPREQ_DEALER_ADDR,
)
from .stats import StatsCollector

_logger = logging.getLogger(__name__)


class TopicBroker:
    """Simple SUB -> PUB forwarder to decouple publishers and subscribers."""

    def __init__(
        self,
        sub_bind: str = FORWARDER_SUB_ADDR,
        pub_bind: str = FORWARDER_PUB_ADDR,
        context: zmq.Context | None = None,
        stats: StatsCollector | None = None,
    ) -> None:
        self.sub_bind = sub_bind
        self.pub_bind = pub_bind
        self._ctx: zmq.Context | None = context or zmq.Context()
        self._owns_context = context is None
        self.stats = stats
        self._thread: threading.Thread | None = None
        self._running = False
        self._frontend: zmq.Socket | None = None
        self._backend: zmq.Socket | None = None

    def start(self) -> None:
        """Start the topic broker.

        Calling this multiple times is safe.
        """
        if self._running:
            return

        if self._ctx is None:
            self._ctx = zmq.Context()

        self._frontend = self._ctx.socket(zmq.SUB)
        self._frontend.bind(self.sub_bind)
        self._frontend.setsockopt_string(zmq.SUBSCRIBE, "")

        self._backend = self._ctx.socket(zmq.PUB)
        self._backend.bind(self.pub_bind)

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        _logger.info("TopicBroker started (%s -> %s)", self.sub_bind, self.pub_bind)

    def stop(self, timeout: float = 1.0) -> None:
        """Stop the topic broker and release bound sockets."""
        if not self._running:
            return

        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

        if self._frontend:
            self._frontend.close(0)
            self._frontend = None

        if self._backend:
            self._backend.close(0)
            self._backend = None

        if self._ctx is not None and self._owns_context:
            self._ctx.destroy(linger=0)
            self._ctx = None

        self._thread = None
        _logger.info("TopicBroker stopped")

    def _run(self) -> None:
        if self._frontend is None or self._backend is None:
            return

        poller = zmq.Poller()
        poller.register(self._frontend, zmq.POLLIN)

        try:
            while self._running:
                sockets = dict(poller.poll(100))

                if self._frontend in sockets:
                    message = self._frontend.recv_multipart()

                    topic = message[0].decode(errors="replace") if message else None
                    payload: Any = None

                    if len(message) > 1:
                        try:
                            payload = json.loads(message[1].decode())
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            payload = {
                                "raw": message[1].decode(errors="replace"),
                            }

                    if self.stats is not None:
                        sender = (
                            payload.get("sender") if isinstance(payload, dict) else None
                        )
                        correlation_id = (
                            payload.get("correlationId")
                            if isinstance(payload, dict)
                            else None
                        )

                        self.stats.record_message(
                            message_type="event",
                            sender=sender,
                            topic=topic,
                            correlation_id=correlation_id,
                            payload=payload,
                            direction="pubsub",
                        )

                    self._backend.send_multipart(message)

        except zmq.error.ContextTerminated:
            pass
        except zmq.error.ZMQError as exc:
            if self._running:
                _logger.error("TopicBroker error: %s", exc, exc_info=True)


_run_topic_broker_singleton: TopicBroker | None = None


def run_topic_broker(*, restart: bool = False) -> TopicBroker:
    """Start a process-wide TopicBroker and return it.

    This helper is mainly intended for demos/simple scripts. For tests and
    applications that need explicit lifecycle control, instantiate TopicBroker
    directly and call start()/stop().

    Args:
        restart: If True, stop the existing singleton broker and create a new one.
    """
    global _run_topic_broker_singleton

    if restart and _run_topic_broker_singleton is not None:
        _run_topic_broker_singleton.stop()
        _run_topic_broker_singleton = None

    if _run_topic_broker_singleton is None:
        _run_topic_broker_singleton = TopicBroker()
        _run_topic_broker_singleton.start()

    return _run_topic_broker_singleton


def stop_topic_broker() -> None:
    """Stop the process-wide TopicBroker if it is running."""
    global _run_topic_broker_singleton

    if _run_topic_broker_singleton is not None:
        _run_topic_broker_singleton.stop()
        _run_topic_broker_singleton = None


class CentralBroker:
    """ROUTER-based broker for request/reply frames."""

    def __init__(
        self,
        bind: str = REPREQ_DEALER_ADDR,
        stats: StatsCollector | None = None,
    ) -> None:
        self.bind = bind
        self.stats = stats
        self._ctx: zmq.Context | None = None
        self._owns_context = True
        self._router: zmq.Socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start the request/reply broker.

        Calling this multiple times is safe.
        """
        if self._running:
            return

        self._ctx = zmq.Context()
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.setsockopt(zmq.ROUTER_MANDATORY, 1)
        self._router.bind(self.bind)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        _logger.info("CentralBroker started on %s", self.bind)

    def stop(self, timeout: float = 1.0) -> None:
        """Stop the request/reply broker and release the bound socket."""
        if not self._running:
            return

        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

        if self._router:
            self._router.close(0)
            self._router = None

        if self._ctx is not None and self._owns_context:
            self._ctx.destroy(linger=0)
            self._ctx = None

        self._thread = None
        _logger.info("CentralBroker stopped")

    def _loop(self) -> None:
        if self._router is None:
            return

        poller = zmq.Poller()
        poller.register(self._router, zmq.POLLIN)

        try:
            while self._running:
                sockets = dict(poller.poll(100))

                if self._router not in sockets:
                    continue

                frames = self._router.recv_multipart()

                if len(frames) < 5:
                    continue

                sender, _, target, _, *payload = frames

                decoded_sender = sender.decode(errors="replace")
                decoded_target = target.decode(errors="replace")
                decoded_payload: Any = None
                correlation_id = None
                message_type = "request"

                if payload:
                    try:
                        decoded_payload = json.loads(payload[0].decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        decoded_payload = {
                            "raw": payload[0].decode(errors="replace"),
                        }

                    if isinstance(decoded_payload, dict):
                        correlation_id = decoded_payload.get("correlationId")

                if decoded_target == INTRABUS_NODE_MODULE:
                    message_type = "system"

                if self.stats is not None:
                    self.stats.record_message(
                        message_type=message_type,
                        sender=decoded_sender,
                        target=decoded_target,
                        correlation_id=correlation_id,
                        payload=decoded_payload,
                        direction="reqrep",
                    )

                outgoing = [target, b"", sender, b"", *payload]

                try:
                    self._router.send_multipart(outgoing)
                except zmq.ZMQError as exc:
                    if self.stats is not None:
                        self.stats.record_delivery_failure(
                            sender=decoded_sender,
                            target=decoded_target,
                            correlation_id=correlation_id,
                            reason=str(exc),
                        )

        except zmq.error.ContextTerminated:
            pass
        except zmq.error.ZMQError as exc:
            if self._running:
                _logger.error("CentralBroker error: %s", exc, exc_info=True)


_run_central_broker_singleton: CentralBroker | None = None


def run_central_broker(*, restart: bool = False) -> CentralBroker:
    """Start a process-wide CentralBroker and return it.

    This helper is mainly intended for demos/simple scripts. For tests and
    applications that need explicit lifecycle control, instantiate CentralBroker
    directly and call start()/stop().

    Args:
        restart: If True, stop the existing singleton broker and create a new one.
    """
    global _run_central_broker_singleton

    if restart and _run_central_broker_singleton is not None:
        _run_central_broker_singleton.stop()
        _run_central_broker_singleton = None

    if _run_central_broker_singleton is None:
        _run_central_broker_singleton = CentralBroker()
        _run_central_broker_singleton.start()

    return _run_central_broker_singleton


def stop_central_broker() -> None:
    """Stop the process-wide CentralBroker if it is running."""
    global _run_central_broker_singleton

    if _run_central_broker_singleton is not None:
        _run_central_broker_singleton.stop()
        _run_central_broker_singleton = None
