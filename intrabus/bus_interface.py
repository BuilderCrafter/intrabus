"""User‑facing API to intrabus – synchronous version.

Provides:
• `publish(topic, data)` / `subscribe(topic, callback)`
• `send_request(target, payload, timeout)` with correlation‑ID tracking

ZeroMQ socket rules are hidden behind background threads.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from queue import Empty, Queue
from typing import Any, Callable, Dict, Optional

import zmq

from .config import (
    FORWARDER_PUB_ADDR,
    FORWARDER_SUB_ADDR,
    REPREQ_DEALER_ADDR,
)

logger = logging.getLogger(__name__)


class BusInterface:  # pylint: disable=too-many-instance-attributes
    """Connect a module to intrabus.

    Parameters
    ----------
    module_name:
        Identity shown to the CentralBroker.
    request_handler:
        Optional callback executed **when this module receives a request**.
        Signature::
            def handler(payload: dict) -> dict | None
    """

    # ---------------------------------------------------------------------
    def __init__(
        self,
        module_name: str,
        *,
        pubsub_forwarder_sub_addr: str = FORWARDER_SUB_ADDR,
        pubsub_forwarder_pub_addr: str = FORWARDER_PUB_ADDR,
        reqrep_broker_addr: str = REPREQ_DEALER_ADDR,
        request_handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.module_name = module_name
        self.request_handler = request_handler
        self._ctx = zmq.Context.instance()

        # PUB → TopicBroker
        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.connect(pubsub_forwarder_sub_addr)

        # SUB ← TopicBroker
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(pubsub_forwarder_pub_addr)

        # DEALER ↔ CentralBroker
        self._rr = self._ctx.socket(zmq.DEALER)
        self._rr.setsockopt_string(zmq.IDENTITY, module_name)
        self._rr.connect(reqrep_broker_addr)

        # background state
        self._sub_callbacks: dict[str, list[Callable[[str, Any], None]]] = {}
        self._sub_running = True
        self._rr_running = True
        self._tx_queue: Queue[list[bytes]] = Queue()
        self._pending: Dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

        # threads
        self._sub_thr = threading.Thread(target=self._sub_loop, daemon=True)
        self._sub_thr.start()
        self._io_thr = threading.Thread(target=self._io_loop, daemon=True)
        self._io_thr.start()

    # ─────────────────────────────── Pub/Sub ──────────────────────────────
    def publish(self, topic: str, message: Any) -> None:
        self._pub.send_multipart(
            [topic.encode(), json.dumps(message).encode()]
        )

    def subscribe(self, topic: str, callback: Callable[[str, Any], None]) -> None:
        self._sub.setsockopt_string(zmq.SUBSCRIBE, topic)
        self._sub_callbacks.setdefault(topic, []).append(callback)

    def _sub_loop(self) -> None:
        while self._sub_running:
            try:
                topic_b, data_b = self._sub.recv_multipart()
            except zmq.error.ContextTerminated:
                break
            topic = topic_b.decode()
            try:
                payload = json.loads(data_b)
            except json.JSONDecodeError:
                payload = {"raw": data_b.decode()}
            for cb in self._sub_callbacks.get(topic, []):
                try:
                    cb(topic, payload)
                except Exception:  # noqa: BLE001
                    logger.exception("Subscriber callback error")

    # ─────────────────────────────── Req/Rep ──────────────────────────────
    def send_request(
        self,
        target: str,
        payload: Dict[str, Any],
        *,
        timeout: float = 1.0,
    ) -> Dict[str, Any]:
        corr = str(uuid.uuid4())
        payload |= {"correlationId": corr, "sender": self.module_name}
        frames = [b"", target.encode(), b"", json.dumps(payload).encode()]
        self._tx_queue.put(frames)

        evt = threading.Event()
        with self._lock:
            self._pending[corr] = {"evt": evt, "reply": None}
        if not evt.wait(timeout):
            with self._lock:
                self._pending.pop(corr, None)
            return {"error": "timeout", "correlationId": corr}
        with self._lock:
            reply = self._pending.pop(corr)["reply"]
        return reply

    def _handle_rr_frames(self, frames: list[bytes]) -> None:
        if len(frames) < 4:
            return
        sender = frames[1].decode()
        raw = frames[3].decode()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            msg = {"raw": raw}
        corr = msg.get("correlationId")

        # is it a reply?
        with self._lock:
            if corr in self._pending:
                self._pending[corr]["reply"] = msg
                self._pending[corr]["evt"].set()
                return

        # else treat as new request
        if self.request_handler is None:
            return
        try:
            reply = self.request_handler(msg) or {}
        except Exception as exc:  # noqa: BLE001
            reply = {"error": str(exc)}
        reply |= {"correlationId": corr, "sender": self.module_name}
        self._tx_queue.put([b"", sender.encode(), b"", json.dumps(reply).encode()])

    # ─────────────────────────────── I/O Loop ─────────────────────────────
    def _io_loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._rr, zmq.POLLIN)
        while self._rr_running:
            # flush outbound
            try:
                while True:
                    frames = self._tx_queue.get_nowait()
                    self._rr.send_multipart(frames)
            except Empty:
                pass

            # poll inbound
            socks = dict(poller.poll(10))
            if self._rr in socks:
                self._handle_rr_frames(self._rr.recv_multipart())

    # ─────────────────────────────── Cleanup ──────────────────────────────
    def stop(self) -> None:
        self._sub_running = False
        self._rr_running = False
        time.sleep(0.05)
        for thr in (self._sub_thr, self._io_thr):
            if thr.is_alive():
                thr.join(timeout=0.5)
        self._pub.close(0)
        self._sub.close(0)
        self._rr.close(0)
        logger.info("[%s] interface stopped", self.module_name)

    # allow `with` usage ----------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        self.stop()
        return False