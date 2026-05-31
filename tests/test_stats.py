from intrabus import StatsCollector


def test_stats_collector_records_message_metadata():
    stats = StatsCollector()

    stats.record_message(
        message_type="request",
        sender="client",
        target="server",
        correlation_id="abc",
        payload={"ping": True},
        direction="reqrep",
    )

    data = stats.to_dict()

    assert data["totalMessages"] == 1
    assert data["totalRequests"] == 1
    assert data["perModule"]["client"]["messagesSent"] == 1
    assert data["perModule"]["server"]["messagesReceived"] == 1
    assert data["recentMessages"][0]["sender"] == "client"
    assert data["recentMessages"][0]["target"] == "server"
    assert "payload" not in data["recentMessages"][0]


def test_stats_collector_can_capture_payloads_when_enabled():
    stats = StatsCollector(capture_payloads=True)

    stats.record_message(
        message_type="event",
        sender="sensor",
        topic="temperature",
        payload={"value": 22.5},
        direction="pubsub",
    )

    data = stats.to_dict()

    assert data["totalMessages"] == 1
    assert data["totalEvents"] == 1
    assert data["perTopic"]["temperature"]["messages"] == 1
    assert data["recentMessages"][0]["payload"] == {"value": 22.5}


def test_stats_collector_recent_messages_are_bounded():
    stats = StatsCollector(max_recent_messages=2)

    stats.record_message(message_type="event", sender="a", topic="x")
    stats.record_message(message_type="event", sender="b", topic="x")
    stats.record_message(message_type="event", sender="c", topic="x")

    data = stats.to_dict()

    assert len(data["recentMessages"]) == 2
    assert data["recentMessages"][0]["sender"] == "b"
    assert data["recentMessages"][1]["sender"] == "c"


def test_stats_collector_records_timeouts():
    stats = StatsCollector()

    stats.record_timeout(
        module_name="client",
        target="server",
        correlation_id="abc",
    )

    data = stats.to_dict()

    assert data["totalTimeouts"] == 1
    assert data["perModule"]["client"]["timeouts"] == 1
    assert data["recentEvents"][0]["type"] == "request.timeout"


def test_stats_collector_reset_clears_state():
    stats = StatsCollector()

    stats.record_message(message_type="event", sender="sensor", topic="temperature")
    stats.record_error(module_name="sensor", error="boom")

    stats.reset()

    data = stats.to_dict()

    assert data["totalMessages"] == 0
    assert data["totalErrors"] == 0
    assert data["perModule"] == {}
    assert data["perTopic"] == {}
    assert data["recentEvents"] == []
    assert data["recentMessages"] == []


def test_stats_collector_records_latency():
    stats = StatsCollector()

    stats.record_latency(
        latency_ms=12.5,
        sender="client",
        target="server",
        correlation_id="abc",
    )

    data = stats.to_dict()

    assert data["latencySamples"] == 1
    assert data["averageLatencyMs"] == 12.5
    assert data["maxLatencyMs"] == 12.5
    assert data["recentEvents"][0]["type"] == "request.latency"


def test_stats_collector_records_delivery_failure():
    stats = StatsCollector()

    stats.record_delivery_failure(
        sender="client",
        target="missing",
        correlation_id="abc",
        reason="unknown target",
    )

    data = stats.to_dict()

    assert data["totalDeliveryFailures"] == 1
    assert data["totalErrors"] == 1
    assert data["perModule"]["client"]["errors"] == 1
    assert data["recentEvents"][0]["type"] == "delivery.failure"
