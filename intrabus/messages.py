from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Self, get_args

MessageType = Literal["event", "request", "reply", "error", "system", "heartbeat"]
VALID_MESSAGE_TYPES = set(get_args(MessageType))

DEFAULT_NODE_ID = "local"
DEFAULT_TTL = 16


@dataclass(slots=True)
class MessageEnvelope:
    """Standard intrabus message envelope"""

    sender: str
    message_type: MessageType
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None
    target: str | None = None
    topic: str | None = None
    timestamp: float = field(default_factory=time.time)
    source_node: str = DEFAULT_NODE_ID
    target_node: str | None = None
    ttl: int = DEFAULT_TTL
    hop_path: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def event(
        cls,
        *,
        sender: str,
        topic: str,
        payload: dict[str, Any],
        source_node: str = DEFAULT_NODE_ID,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create a publish/subscribe event envelope."""
        return cls(
            sender=sender,
            topic=topic,
            payload=payload,
            message_type="event",
            source_node=source_node,
            ttl=ttl,
        )

    @classmethod
    def request(
        cls,
        *,
        sender: str,
        target: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        source_node: str = DEFAULT_NODE_ID,
        target_node: str | None = None,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create a request envelope."""
        return cls(
            sender=sender,
            target=target,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
            message_type="request",
            source_node=source_node,
            target_node=target_node,
            ttl=ttl,
        )

    @classmethod
    def reply(
        cls,
        *,
        sender: str,
        target: str,
        correlation_id: str,
        payload: dict[str, Any],
        source_node: str = DEFAULT_NODE_ID,
        target_node: str | None = None,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create a reply envelope for an existing request correlation ID."""
        return cls(
            sender=sender,
            target=target,
            payload=payload,
            correlation_id=correlation_id,
            message_type="reply",
            source_node=source_node,
            target_node=target_node,
            ttl=ttl,
        )

    @classmethod
    def error(
        cls,
        *,
        sender: str,
        payload: dict[str, Any],
        target: str | None = None,
        correlation_id: str | None = None,
        source_node: str = DEFAULT_NODE_ID,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create an error envelope."""
        return cls(
            sender=sender,
            target=target,
            payload=payload,
            correlation_id=correlation_id,
            message_type="error",
            source_node=source_node,
            ttl=ttl,
        )

    @classmethod
    def system(
        cls,
        *,
        sender: str,
        payload: dict[str, Any],
        target: str | None = "intrabus.node",
        correlation_id: str | None = None,
        source_node: str = DEFAULT_NODE_ID,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create a system/control envelope."""
        return cls(
            sender=sender,
            target=target,
            payload=payload,
            correlation_id=correlation_id,
            message_type="system",
            source_node=source_node,
            ttl=ttl,
        )

    @classmethod
    def heartbeat(
        cls,
        *,
        sender: str,
        payload: dict[str, Any] | None = None,
        source_node: str = DEFAULT_NODE_ID,
        ttl: int = DEFAULT_TTL,
    ) -> Self:
        """Create a heartbeat/liveness envelope."""
        return cls(
            sender=sender,
            payload=payload or {"status": "ok"},
            message_type="heartbeat",
            source_node=source_node,
            ttl=ttl,
        )

    def validate(self) -> None:
        """Validate the envelope's basic structural invariants."""
        if not self.message_id:
            raise ValueError("message_id is required")
        if not self.sender:
            raise ValueError("sender is required")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dictionary")
        if self.message_type not in VALID_MESSAGE_TYPES:
            raise ValueError(f"invalid message_type: {self.message_type}")
        if self.ttl < 0:
            raise ValueError("ttl must be greater than or equal to 0")
        if self.message_type == "event" and not self.topic:
            raise ValueError("event messages require a topic")
        if self.message_type == "request" and not self.target:
            raise ValueError("request messages require a target")
        if self.message_type == "reply":
            if not self.target:
                raise ValueError("reply messages require a target")
            if not self.correlation_id:
                raise ValueError("reply messages require a correlation_id")

    def with_hop(self, node_id: str) -> Self:
        """Return a copy of the envelope with one node hop appended.

        This is not used by the current single-node broker yet, but it provides
        the basic primitive needed later for loop detection and multi-node
        routing.
        """
        data = self.to_dict()
        data["hopPath"] = [*self.hop_path, node_id]
        data["ttl"] = self.ttl - 1
        return self.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to the camelCase wire format."""
        return {
            "messageId": self.message_id,
            "correlationId": self.correlation_id,
            "sender": self.sender,
            "target": self.target,
            "topic": self.topic,
            "messageType": self.message_type,
            "timestamp": self.timestamp,
            "sourceNode": self.source_node,
            "targetNode": self.target_node,
            "ttl": self.ttl,
            "hopPath": list(self.hop_path),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize an envelope from the camelCase wire format."""
        return cls(
            message_id=data.get("messageId", ""),
            correlation_id=data.get("correlationId"),
            sender=data.get("sender", ""),
            target=data.get("target"),
            topic=data.get("topic"),
            message_type=data.get("messageType"),
            timestamp=data.get("timestamp", time.time()),
            source_node=data.get("sourceNode", DEFAULT_NODE_ID),
            target_node=data.get("targetNode"),
            ttl=data.get("ttl", DEFAULT_TTL),
            hop_path=list(data.get("hopPath", [])),
            payload=data.get("payload", {}),
        )

    def to_json(self) -> str:
        """Serialize the envelope to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        """Deserialize an envelope from a JSON string or bytes."""
        if isinstance(data, bytes):
            data = data.decode()
        return cls.from_dict(json.loads(data))
