"""ZeroMQ broker helpers used by intrabus.

`TopicBroker`  – a PUB/SUB forwarder (aka "XSUB↔XPUB" pattern).
`CentralBroker` – a ROUTER‑based request/reply router.
Both can be started programmatically or via helper runners.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import zmq

from .config import (
    FORWARDER_PUB_ADDR,
    FORWARDER_SUB_ADDR,
    REPREQ_DEALER_ADDR,
)

_logger = logging.getLogger(__name__)


# ───────────────────────────────────────── TopicBroker ──────────────────────────────────────────
class TopicBroker:
    """Simple XSUB↔XPUB forwarder to decouple publishers & subscribers."""

    def __init__(
        self,
        sub_bind: str = FORWARDER_SUB_ADDR,
        pub_bind: str = FORWARDER_PUB_ADDR,
        context: Optional[zmq.Context] = None,
    ) -> None:
        self.sub_bind = sub_bind
        self.pub_bind = pub_bind
        self._ctx = context or zmq.Context.instance()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # public helpers ---------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        _logger.info("TopicBroker started (%s → %s)", self.sub_bind, self.pub_bind)

    def stop(self, timeout: float = 1.0) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)
        _logger.info("TopicBroker stopped")

    # internals --------------------------------------------------------------
    def _run(self) -> None:  # pylint: disable=too-many-locals
        frontend = self._ctx.socket(zmq.SUB)
        frontend.bind(self.sub_bind)
        frontend.setsockopt_string(zmq.SUBSCRIBE, "")  # receive all topics

        backend = self._ctx.socket(zmq.PUB)
        backend.bind(self.pub_bind)

        try:
            zmq.proxy(frontend, backend)
        except KeyboardInterrupt:
            pass
        finally:
            frontend.close()
            backend.close()


# convenience runner
_run_topic_broker_singleton: Optional[TopicBroker] = None

def run_topic_broker() -> TopicBroker:  # noqa: D401
    """Start a singleton TopicBroker in‑process and return it."""
    global _run_topic_broker_singleton  # pylint: disable=global-statement
    if _run_topic_broker_singleton is None:
        _run_topic_broker_singleton = TopicBroker()
        _run_topic_broker_singleton.start()
    return _run_topic_broker_singleton


# ──────────────────────────────────────── CentralBroker ─────────────────────────────────────────
class CentralBroker:
    """ROUTER‑based broker for request/reply frames."""

    def __init__(self, bind: str = REPREQ_DEALER_ADDR) -> None:
        self.bind = bind
        self._ctx: Optional[zmq.Context] = None
        self._router: Optional[zmq.Socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # public helpers ---------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._ctx = zmq.Context.instance()
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.bind(self.bind)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        _logger.info("CentralBroker started on %s", self.bind)

    def stop(self, timeout: float = 1.0) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)
        if self._router:
            self._router.close(0)
        _logger.info("CentralBroker stopped")

    # internals --------------------------------------------------------------
    def _loop(self) -> None:
        assert self._router is not None  # for type checkers
        try:
            while self._running:
                frames = self._router.recv_multipart(flags=0)
                if len(frames) < 5:
                    continue  # malformed
                sender, _, target, _, *payload = frames
                out = [target, b"", sender, b""] + payload
                self._router.send_multipart(out)
        except zmq.error.ContextTerminated:
            pass
        except Exception as exc:  # noqa: BLE001
            _logger.error("CentralBroker error: %s", exc, exc_info=True)


# convenience runner
_run_central_broker_singleton: Optional[CentralBroker] = None

def run_central_broker() -> CentralBroker:  # noqa: D401
    """Start a singleton CentralBroker in‑process and return it."""
    global _run_central_broker_singleton  # pylint: disable=global-statement
    if _run_central_broker_singleton is None:
        _run_central_broker_singleton = CentralBroker()
        _run_central_broker_singleton.start()
    return _run_central_broker_singleton