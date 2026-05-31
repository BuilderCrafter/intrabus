from intrabus import DiagnosticsManager, ModuleRegistry, StatsCollector


def test_diagnostics_manager_reports_offline_modules():
    registry = ModuleRegistry(node_id="test_node")
    stats = StatsCollector()
    diagnostics = DiagnosticsManager()

    registry.register("sensor_1")
    registry.unregister("sensor_1")

    diagnostics.refresh_from_runtime(
        registry=registry,
        stats=stats,
    )

    data = diagnostics.to_dict()

    assert data["count"] == 1
    assert data["diagnostics"][0]["code"] == "MODULE_OFFLINE"
    assert data["diagnostics"][0]["severity"] == "warning"
    assert data["diagnostics"][0]["module"] == "sensor_1"


def test_diagnostics_manager_reports_request_timeouts():
    registry = ModuleRegistry(node_id="test_node")
    stats = StatsCollector()
    diagnostics = DiagnosticsManager()

    stats.record_timeout(
        module_name="client",
        target="server",
        correlation_id="abc",
    )

    diagnostics.refresh_from_runtime(
        registry=registry,
        stats=stats,
    )

    data = diagnostics.to_dict()

    assert data["count"] == 1
    assert data["diagnostics"][0]["code"] == "REQUEST_TIMEOUT"
    assert data["diagnostics"][0]["severity"] == "warning"
    assert data["diagnostics"][0]["module"] == "client"


def test_diagnostics_manager_reports_handler_errors():
    registry = ModuleRegistry(node_id="test_node")
    stats = StatsCollector()
    diagnostics = DiagnosticsManager()

    stats.record_error(
        module_name="server",
        error="boom",
        correlation_id="abc",
    )

    diagnostics.refresh_from_runtime(
        registry=registry,
        stats=stats,
    )

    data = diagnostics.to_dict()

    assert data["count"] == 1
    assert data["diagnostics"][0]["code"] == "HANDLER_ERROR"
    assert data["diagnostics"][0]["severity"] == "error"
    assert data["diagnostics"][0]["module"] == "server"


def test_diagnostics_manager_reports_delivery_failures():
    registry = ModuleRegistry(node_id="test_node")
    stats = StatsCollector()
    diagnostics = DiagnosticsManager()

    stats.record_delivery_failure(
        sender="client",
        target="missing",
        correlation_id="abc",
        reason="Host unreachable",
    )

    diagnostics.refresh_from_runtime(
        registry=registry,
        stats=stats,
    )

    data = diagnostics.to_dict()

    assert data["count"] == 1
    assert data["diagnostics"][0]["code"] == "DELIVERY_FAILURE"
    assert data["diagnostics"][0]["severity"] == "error"
    assert data["diagnostics"][0]["module"] == "client"
