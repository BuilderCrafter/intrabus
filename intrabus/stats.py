from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .config import INTRABUS_NODE_MODULE

INTERNAL_COMMANDS = {
    "module.register",
    "module.unregister",
    "module.heartbeat",
    "node.get_health",
    "node.get_registry",
    "node.get_stats",
    "node.get_diagnostics",
    "node.reset_stats",
    "node.clear_diagnostics",
    "registry.get",
    "registry.health",
    "stats.get",
    "stats.reset",
    "diagnostics.get",
    "diagnostics.clear",
}


@dataclass
class ModuleStats:
    messages_sent: int = 0
    messages_received: int = 0
    requests_sent: int = 0
    requests_received: int = 0
    replies_sent: int = 0
    replies_received: int = 0
    timeouts: int = 0
    errors: int = 0


@dataclass
class TopicStats:
    messages: int = 0


@dataclass
class StatsCollector:
    max_recent_events: int = 1000
    max_recent_messages: int = 500
    capture_payloads: bool = False

    total_messages: int = 0
    total_requests: int = 0
    total_replies: int = 0
    total_timeouts: int = 0
    total_errors: int = 0
    total_events: int = 0

    total_latency_ms: float = 0.0
    latency_samples: int = 0
    max_latency_ms: float = 0.0
    total_delivery_failures: int = 0

    per_module: dict[str, ModuleStats] = field(default_factory=dict)
    per_topic: dict[str, TopicStats] = field(default_factory=dict)

    recent_events: deque[dict[str, Any]] = field(init=False)
    recent_messages: deque[dict[str, Any]] = field(init=False)

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self.recent_events = deque(maxlen=self.max_recent_events)
        self.recent_messages = deque(maxlen=self.max_recent_messages)

    def record_message(
        self,
        *,
        message_type: str,
        sender: str | None = None,
        target: str | None = None,
        topic: str | None = None,
        correlation_id: str | None = None,
        payload: Any = None,
        direction: str | None = None,
        status: str = "ok",
    ) -> None:
        if self.is_internal_message(
            message_type=message_type,
            sender=sender,
            target=target,
            payload=payload,
            direction=direction,
        ):
            return

        payload_size = self._payload_size(payload)

        with self._lock:
            self.total_messages += 1

            if message_type == "event":
                self.total_events += 1
            elif message_type == "request":
                self.total_requests += 1
            elif message_type == "reply":
                self.total_replies += 1
            elif message_type == "error":
                self.total_errors += 1

            if sender:
                module = self._module(sender)
                module.messages_sent += 1

                if message_type == "request":
                    module.requests_sent += 1
                elif message_type == "reply":
                    module.replies_sent += 1
                elif message_type == "error":
                    module.errors += 1

            if target:
                module = self._module(target)
                module.messages_received += 1

                if message_type == "request":
                    module.requests_received += 1
                elif message_type == "reply":
                    module.replies_received += 1

            if topic:
                self._topic(topic).messages += 1

            message = {
                "timestamp": time.time(),
                "messageType": message_type,
                "direction": direction,
                "sender": sender,
                "target": target,
                "topic": topic,
                "correlationId": correlation_id,
                "payloadSize": payload_size,
                "status": status,
            }

            if self.capture_payloads:
                message["payload"] = payload

            self.recent_messages.append(message)
            self.recent_events.append(
                {
                    "timestamp": message["timestamp"],
                    "type": f"{message_type}.recorded",
                    "sender": sender,
                    "target": target,
                    "topic": topic,
                    "correlationId": correlation_id,
                    "metadata": {
                        "payloadSize": payload_size,
                        "status": status,
                    },
                }
            )

    def record_timeout(
        self,
        *,
        module_name: str | None = None,
        target: str | None = None,
        correlation_id: str | None = None,
        payload: Any = None,
    ) -> None:
        if self.is_internal_message(
            message_type="request",
            sender=module_name,
            target=target,
            payload=payload,
            direction="reqrep",
        ):
            return

        with self._lock:
            self.total_timeouts += 1

            if module_name:
                self._module(module_name).timeouts += 1

            self.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": "request.timeout",
                    "module": module_name,
                    "target": target,
                    "correlationId": correlation_id,
                    "metadata": {},
                }
            )

    def record_latency(
        self,
        *,
        latency_ms: float,
        sender: str | None = None,
        target: str | None = None,
        correlation_id: str | None = None,
        payload: Any = None,
    ) -> None:
        if self.is_internal_message(
            message_type="request",
            sender=sender,
            target=target,
            payload=payload,
            direction="reqrep",
        ):
            return

        with self._lock:
            self.total_latency_ms += latency_ms
            self.latency_samples += 1
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)

            self.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": "request.latency",
                    "sender": sender,
                    "target": target,
                    "correlationId": correlation_id,
                    "metadata": {
                        "latencyMs": latency_ms,
                    },
                }
            )

    def record_delivery_failure(
        self,
        *,
        sender: str | None = None,
        target: str | None = None,
        correlation_id: str | None = None,
        reason: str = "delivery_failed",
    ) -> None:
        with self._lock:
            self.total_delivery_failures += 1
            self.total_errors += 1

            if sender:
                self._module(sender).errors += 1

            self.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": "delivery.failure",
                    "sender": sender,
                    "target": target,
                    "correlationId": correlation_id,
                    "metadata": {
                        "reason": reason,
                    },
                }
            )

    def record_error(
        self,
        *,
        module_name: str | None = None,
        error: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        with self._lock:
            self.total_errors += 1

            if module_name:
                self._module(module_name).errors += 1

            self.recent_events.append(
                {
                    "timestamp": time.time(),
                    "type": "error",
                    "module": module_name,
                    "correlationId": correlation_id,
                    "metadata": {
                        "error": error,
                    },
                }
            )

    def reset(self) -> None:
        with self._lock:
            self.total_messages = 0
            self.total_requests = 0
            self.total_replies = 0
            self.total_timeouts = 0
            self.total_errors = 0
            self.total_events = 0
            self.total_latency_ms = 0.0
            self.latency_samples = 0
            self.max_latency_ms = 0.0
            self.total_delivery_failures = 0
            self.per_module.clear()
            self.per_topic.clear()
            self.recent_events.clear()
            self.recent_messages.clear()

    def to_dict(self) -> dict[str, Any]:
        average_latency_ms = (
            self.total_latency_ms / self.latency_samples
            if self.latency_samples
            else 0.0
        )

        with self._lock:
            return {
                "totalMessages": self.total_messages,
                "totalRequests": self.total_requests,
                "totalReplies": self.total_replies,
                "totalTimeouts": self.total_timeouts,
                "totalErrors": self.total_errors,
                "totalEvents": self.total_events,
                "averageLatencyMs": average_latency_ms,
                "maxLatencyMs": self.max_latency_ms,
                "latencySamples": self.latency_samples,
                "totalDeliveryFailures": self.total_delivery_failures,
                "perModule": {
                    name: {
                        "messagesSent": stats.messages_sent,
                        "messagesReceived": stats.messages_received,
                        "requestsSent": stats.requests_sent,
                        "requestsReceived": stats.requests_received,
                        "repliesSent": stats.replies_sent,
                        "repliesReceived": stats.replies_received,
                        "timeouts": stats.timeouts,
                        "errors": stats.errors,
                    }
                    for name, stats in self.per_module.items()
                },
                "perTopic": {
                    name: {
                        "messages": stats.messages,
                    }
                    for name, stats in self.per_topic.items()
                },
                "recentEvents": list(self.recent_events),
                "recentMessages": list(self.recent_messages),
            }

    def _module(self, name: str) -> ModuleStats:
        if name not in self.per_module:
            self.per_module[name] = ModuleStats()
        return self.per_module[name]

    def _topic(self, name: str) -> TopicStats:
        if name not in self.per_topic:
            self.per_topic[name] = TopicStats()
        return self.per_topic[name]

    @staticmethod
    def _payload_size(payload: Any) -> int:
        if payload is None:
            return 0

        try:
            return len(json.dumps(payload).encode())
        except TypeError:
            return len(str(payload).encode())

    @staticmethod
    def is_internal_message(
        *,
        message_type: str | None = None,
        sender: str | None = None,
        target: str | None = None,
        payload: Any = None,
        direction: str | None = None,
    ) -> bool:
        if message_type == "system":
            return True

        if direction == "reqrep" and (
            sender == INTRABUS_NODE_MODULE or target == INTRABUS_NODE_MODULE
        ):
            return True

        return isinstance(payload, dict) and payload.get("command") in INTERNAL_COMMANDS
