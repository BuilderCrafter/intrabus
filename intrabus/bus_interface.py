"""User-facing module interface for intrabus communication.

`BusInterface` provides publish/subscribe and request/reply operations while
hiding ZeroMQ socket ownership behind background threads.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any

import zmq

from .config import (
    FORWARDER_PUB_ADDR,
    FORWARDER_SUB_ADDR,
    INTRABUS_NODE_MODULE,
    REPREQ_DEALER_ADDR,
)
from .stats import StatsCollector

logger = logging.getLogger(__name__)


class BusInterface:
    """Connect one application module to intrabus."""

    def __init__(
        self,
        module_name: str,
        *,
        pubsub_forwarder_sub_addr: str = FORWARDER_SUB_ADDR,
        pubsub_forwarder_pub_addr: str = FORWARDER_PUB_ADDR,
        reqrep_broker_addr: str = REPREQ_DEALER_ADDR,
        request_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        auto_register: bool = True,
        enable_heartbeat: bool = True,
        heartbeat_interval: float = 2.0,
        stats: StatsCollector | None = None,
    ) -> None:
        self.module_name = module_name
        self.request_handler = request_handler
        self._ctx = zmq.Context()
        self.stats = stats

        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.connect(pubsub_forwarder_sub_addr)

        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(pubsub_forwarder_pub_addr)

        self._rr = self._ctx.socket(zmq.DEALER)
        self._rr.setsockopt_string(zmq.IDENTITY, module_name)
        self._rr.connect(reqrep_broker_addr)

        self._sub_callbacks: dict[str, list[Callable[[str, Any], None]]] = {}
        self._sub_running = True
        self._rr_running = True
        self._tx_queue: Queue[list[bytes]] = Queue()
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

        self._sub_thr = threading.Thread(target=self._sub_loop, daemon=True)
        self._sub_thr.start()
        self._io_thr = threading.Thread(target=self._io_loop, daemon=True)
        self._io_thr.start()

        self.auto_register = auto_register
        if self.auto_register:
            self._register_with_node()

        self.enable_heartbeat = enable_heartbeat
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_running = False
        self._heartbeat_thr: threading.Thread | None = None

        if self.enable_heartbeat:
            self._start_heartbeat()

    def publish(self, topic: str, message: Any) -> None:
        """Publish a JSON-serializable message on a topic."""
        self._pub.send_multipart([topic.encode(), json.dumps(message).encode()])

    def subscribe(self, topic: str, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to a topic and call `callback` for matching messages."""
        self._sub.setsockopt_string(zmq.SUBSCRIBE, topic)
        self._sub_callbacks.setdefault(topic, []).append(callback)

    def _sub_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._sub, zmq.POLLIN)

        while self._sub_running:
            try:
                socks = dict(poller.poll(100))
            except zmq.error.ContextTerminated:
                break
            except zmq.error.ZMQError:
                if self._sub_running:
                    logger.exception("Subscriber poll error")
                break

            if self._sub not in socks:
                continue

            try:
                topic_b, data_b = self._sub.recv_multipart()
            except zmq.error.ContextTerminated:
                break
            except zmq.error.ZMQError:
                if self._sub_running:
                    logger.exception("Subscriber receive error")
                break

            topic = topic_b.decode()
            try:
                payload = json.loads(data_b)
            except json.JSONDecodeError:
                payload = {"raw": data_b.decode()}

            for callback in self._sub_callbacks.get(topic, []):
                try:
                    callback(topic, payload)
                except Exception:
                    logger.exception("Subscriber callback error")

    def send_request(
        self,
        target: str,
        payload: dict[str, Any],
        *,
        timeout: float = 1.0,
    ) -> dict[str, Any]:
        """Send a request to another module and wait for its reply."""
        correlation_id = str(uuid.uuid4())
        payload |= {"correlationId": correlation_id, "sender": self.module_name}
        frames = [b"", target.encode(), b"", json.dumps(payload).encode()]

        started_at = time.perf_counter()

        self._tx_queue.put(frames)

        event = threading.Event()
        with self._lock:
            self._pending[correlation_id] = {"evt": event, "reply": None}

        if not event.wait(timeout):
            with self._lock:
                self._pending.pop(correlation_id, None)

            if self.stats is not None:
                self.stats.record_timeout(
                    module_name=self.module_name,
                    target=target,
                    correlation_id=correlation_id,
                )

            return {"error": "timeout", "correlationId": correlation_id}

        latency_ms = (time.perf_counter() - started_at) * 1000

        if self.stats is not None:
            self.stats.record_latency(
                latency_ms=latency_ms,
                sender=self.module_name,
                target=target,
                correlation_id=correlation_id,
            )

        with self._lock:
            reply = self._pending.pop(correlation_id)["reply"]
        return reply

    def _handle_rr_frames(self, frames: list[bytes]) -> None:
        if len(frames) < 4:
            return

        sender = frames[1].decode()
        raw = frames[3].decode()

        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            message = {"raw": raw}

        correlation_id = message.get("correlationId")

        with self._lock:
            if correlation_id in self._pending:
                self._pending[correlation_id]["reply"] = message
                self._pending[correlation_id]["evt"].set()
                return

        if self.request_handler is None:
            return

        try:
            reply = self.request_handler(message) or {}
        except Exception as exc:  # noqa: BLE001
            if self.stats is not None:
                self.stats.record_error(
                    module_name=self.module_name,
                    error=str(exc),
                    correlation_id=correlation_id,
                )

            reply = {"error": str(exc)}

        reply |= {"correlationId": correlation_id, "sender": self.module_name}
        self._tx_queue.put([b"", sender.encode(), b"", json.dumps(reply).encode()])

    def _io_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._rr, zmq.POLLIN)

        while self._rr_running:
            try:
                while True:
                    frames = self._tx_queue.get_nowait()
                    self._rr.send_multipart(frames)
            except Empty:
                pass

            socks = dict(poller.poll(10))
            if self._rr in socks:
                self._handle_rr_frames(self._rr.recv_multipart())

    def _register_with_node(self) -> None:
        """Best-effort registration with the local communication node."""
        reply = self.send_request(
            INTRABUS_NODE_MODULE,
            {
                "command": "module.register",
                "moduleName": self.module_name,
                "capabilities": ["pubsub", "reqrep"],
            },
            timeout=0.3,
        )

        if reply.get("error") == "timeout":
            logger.debug("[%s] communication node not available", self.module_name)
            return

        if reply.get("ok") is False:
            logger.warning(
                "[%s] registration failed: %s",
                self.module_name,
                reply.get("error"),
            )

    def _unregister_from_node(self) -> None:
        """Best-effort unregister from the local communication node."""
        reply = self.send_request(
            INTRABUS_NODE_MODULE,
            {
                "command": "module.unregister",
                "moduleName": self.module_name,
            },
            timeout=0.3,
        )

        if reply.get("error") == "timeout":
            logger.debug("[%s] communication node not available", self.module_name)
            return

    def _start_heartbeat(self) -> None:
        """Start the heartbeat background thread."""
        if self._heartbeat_running:
            return

        self._heartbeat_running = True
        self._heartbeat_thr = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thr.start()

    def _heartbeat_loop(self) -> None:
        """Periodically notify the communication node that this module is alive."""
        while self._heartbeat_running:
            time.sleep(self.heartbeat_interval)

            if not self._heartbeat_running:
                break

            self._send_heartbeat()

    def _send_heartbeat(self) -> None:
        """Best-effort heartbeat to the local communication node."""
        reply = self.send_request(
            INTRABUS_NODE_MODULE,
            {
                "command": "module.heartbeat",
                "moduleName": self.module_name,
            },
            timeout=0.3,
        )

        if reply.get("error") == "timeout":
            logger.debug(
                "[%s] heartbeat skipped; communication node not available",
                self.module_name,
            )
            return

        if reply.get("ok") is False:
            logger.warning(
                "[%s] heartbeat failed: %s",
                self.module_name,
                reply.get("error"),
            )

    def stop(self) -> None:
        """Stop background threads and release ZeroMQ resources."""
        self._heartbeat_running = False

        if self._heartbeat_thr and self._heartbeat_thr.is_alive():
            self._heartbeat_thr.join(timeout=1.0)

        if self.auto_register:
            self._unregister_from_node()

        self._sub_running = False
        self._rr_running = False

        for thread in (self._sub_thr, self._io_thr):
            if thread.is_alive():
                thread.join(timeout=1.0)

        self._pub.close(0)
        self._sub.close(0)
        self._rr.close(0)
        self._ctx.destroy(linger=0)

        logger.info("[%s] interface stopped", self.module_name)

    def __enter__(self) -> BusInterface:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.stop()
        return False
