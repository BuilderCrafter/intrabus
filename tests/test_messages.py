import json

import pytest

from intrabus.messages import DEFAULT_NODE_ID, MessageEnvelope


def test_event_envelope_serializes_to_wire_format():
    envelope = MessageEnvelope.event(
        sender="sensor",
        topic="temperature",
        payload={"value": 22.5},
    )

    data = envelope.to_dict()

    assert data["messageId"]
    assert data["sender"] == "sensor"
    assert data["topic"] == "temperature"
    assert data["messageType"] == "event"
    assert data["sourceNode"] == DEFAULT_NODE_ID
    assert data["payload"] == {"value": 22.5}


def test_request_envelope_generates_correlation_id():
    envelope = MessageEnvelope.request(
        sender="client",
        target="service",
        payload={"ping": True},
    )

    assert envelope.message_type == "request"
    assert envelope.target == "service"
    assert envelope.correlation_id is not None


def test_reply_envelope_requires_correlation_id():
    with pytest.raises(ValueError, match="correlation_id"):
        MessageEnvelope(
            sender="service",
            target="client",
            message_type="reply",
            payload={"ok": True},
        )


def test_event_envelope_requires_topic():
    with pytest.raises(ValueError, match="topic"):
        MessageEnvelope(sender="sensor", message_type="event", payload={})


def test_request_envelope_requires_target():
    with pytest.raises(ValueError, match="target"):
        MessageEnvelope(sender="client", message_type="request", payload={})


def test_payload_must_be_dict():
    with pytest.raises(TypeError, match="payload"):
        MessageEnvelope(sender="sensor", message_type="heartbeat", payload="bad")


def test_roundtrip_from_json():
    original = MessageEnvelope.request(
        sender="client",
        target="service",
        payload={"ping": True},
        source_node="edge-1",
        target_node="edge-2",
    )

    restored = MessageEnvelope.from_json(original.to_json())

    assert restored == original


def test_from_json_accepts_bytes():
    original = MessageEnvelope.heartbeat(sender="module-a")

    restored = MessageEnvelope.from_json(original.to_json().encode())

    assert restored == original


def test_with_hop_appends_node_and_decrements_ttl():
    envelope = MessageEnvelope.request(
        sender="client",
        target="service",
        payload={"ping": True},
        ttl=3,
    )

    updated = envelope.with_hop("node-a")

    assert updated.hop_path == ["node-a"]
    assert updated.ttl == 2
    assert envelope.hop_path == []
    assert envelope.ttl == 3


def test_to_json_outputs_valid_json():
    envelope = MessageEnvelope.system(
        sender="module-a",
        payload={"command": "module.register"},
    )

    decoded = json.loads(envelope.to_json())

    assert decoded["messageType"] == "system"
    assert decoded["target"] == "intrabus.node"


def test_envelope_rejects_unknown_message_type():
    with pytest.raises(ValueError, match="invalid message_type"):
        MessageEnvelope(sender="module", message_type="unknown", payload={})
