import time

from intrabus import BusInterface, CentralBroker, CommunicationNode, TopicBroker


def make_test_node(node_id: str) -> CommunicationNode:
    return CommunicationNode(
        node_id,
        topic_broker=TopicBroker(
            sub_bind="tcp://127.0.0.1:15558",
            pub_bind="tcp://127.0.0.1:15559",
        ),
        central_broker=CentralBroker(
            bind="tcp://127.0.0.1:15560",
        ),
    )


def test_communication_node_has_registry():
    node = CommunicationNode("test_node")

    assert node.registry.node_id == "test_node"
    assert node.registry.list_modules() == []


def test_communication_node_starts_and_stops():
    node = make_test_node("test_node")

    assert node.node_id == "test_node"
    assert node.is_running is False

    node.start()
    assert node.is_running is True

    node.stop()
    assert node.is_running is False


def test_communication_node_is_idempotent():
    node = make_test_node("test_node")

    node.start()
    node.start()

    assert node.is_running is True

    node.stop()
    node.stop()

    assert node.is_running is False


def test_communication_node_context_manager():
    with make_test_node("test_node") as node:
        assert node.is_running is True

    assert node.is_running is False


def test_communication_node_supports_existing_reqrep_flow():
    with make_test_node("test_node"):
        srv = BusInterface(
            "srv",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            request_handler=lambda msg: {"pong": True},
        )
        cli = BusInterface(
            "cli",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
        )

        try:
            reply = cli.send_request("srv", {"ping": True}, timeout=2)
            assert reply.get("pong") is True
        finally:
            srv.stop()
            cli.stop()


def test_bus_interface_auto_registers_with_node():
    with CommunicationNode("test_node") as node:
        module = BusInterface("sensor_1")

        try:
            assert node.registry.contains("sensor_1") is True

            registered = node.registry.get("sensor_1")
            assert registered is not None
            assert registered.module_name == "sensor_1"
            assert registered.status == "online"
        finally:
            module.stop()


def test_bus_interface_unregisters_on_stop():
    with CommunicationNode("test_node") as node:
        module = BusInterface("sensor_1")

        module.stop()

        registered = node.registry.get("sensor_1")
        assert registered is not None
        assert registered.status == "offline"


def test_node_registry_get_command():
    with CommunicationNode("test_node"):
        module = BusInterface("sensor_1")
        client = BusInterface("client")

        try:
            reply = client.send_request(
                "intrabus.node",
                {"command": "registry.get"},
                timeout=2,
            )

            assert reply["ok"] is True
            assert reply["registry"]["nodeId"] == "test_node"
            assert "sensor_1" in reply["registry"]["modules"]
        finally:
            module.stop()
            client.stop()


def test_duplicate_module_registration_returns_error():
    with CommunicationNode("test_node"):
        first = BusInterface("sensor_1")
        client = BusInterface("client", auto_register=False)

        try:
            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "module.register",
                    "moduleName": "sensor_1",
                },
                timeout=2,
            )

            assert reply["ok"] is False
            assert "already registered" in reply["error"]
        finally:
            first.stop()
            client.stop()


def test_heartbeat_updates_last_seen():
    with CommunicationNode("test_node") as node:
        module = BusInterface(
            "sensor_1",
            heartbeat_interval=0.1,
        )

        try:
            registered = node.registry.get("sensor_1")
            assert registered is not None
            initial_last_seen = registered.last_seen

            time.sleep(0.25)

            updated = node.registry.get("sensor_1")
            assert updated is not None
            assert updated.last_seen > initial_last_seen
            assert updated.status == "online"
        finally:
            module.stop()


def test_heartbeat_can_register_unknown_module():
    with CommunicationNode("test_node") as node:
        client = BusInterface("client", auto_register=False, enable_heartbeat=False)

        try:
            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "module.heartbeat",
                    "moduleName": "unknown_module",
                },
                timeout=2,
            )

            assert reply["ok"] is True
            assert node.registry.contains("unknown_module") is True
            assert node.registry.get("unknown_module").status == "online"
        finally:
            client.stop()


def test_registry_health_command_marks_stale_modules_offline():
    with CommunicationNode("test_node") as node:
        module = BusInterface(
            "sensor_1",
            enable_heartbeat=False,
        )
        client = BusInterface(
            "client",
            enable_heartbeat=False,
        )

        try:
            registered = node.registry.get("sensor_1")
            assert registered is not None
            registered.last_seen -= 10

            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "registry.health",
                    "timeoutSeconds": 5,
                },
                timeout=2,
            )

            assert reply["ok"] is True
            assert "sensor_1" in reply["staleModules"]
            assert node.registry.get("sensor_1").status == "offline"
        finally:
            module.stop()
            client.stop()


def test_node_stats_get_command_returns_stats():
    with make_test_node("test_node"):
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            reply = client.send_request(
                "intrabus.node",
                {"command": "stats.get"},
                timeout=2,
            )

            assert reply["ok"] is True
            assert "stats" in reply
            assert "totalMessages" in reply["stats"]
            assert "recentMessages" in reply["stats"]
        finally:
            client.stop()


def test_node_diagnostics_get_command_returns_diagnostics():
    with make_test_node("test_node") as node:
        module = BusInterface(
            "sensor_1",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            registered = node.registry.get("sensor_1")
            assert registered is not None
            registered.last_seen -= 10

            health_reply = client.send_request(
                "intrabus.node",
                {
                    "command": "registry.health",
                    "timeoutSeconds": 5,
                },
                timeout=2,
            )

            assert health_reply["ok"] is True

            diagnostics_reply = client.send_request(
                "intrabus.node",
                {
                    "command": "diagnostics.get",
                },
                timeout=2,
            )

            assert diagnostics_reply["ok"] is True

            diagnostics = diagnostics_reply["diagnostics"]["diagnostics"]
            codes = {diagnostic["code"] for diagnostic in diagnostics}

            assert "MODULE_OFFLINE" in codes
        finally:
            module.stop()
            client.stop()


def test_node_get_health_command_returns_compact_node_state():
    with make_test_node("test_node"):
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "node.get_health",
                    "timeoutSeconds": 5,
                },
                timeout=2,
            )

            assert reply["ok"] is True
            assert reply["nodeId"] == "test_node"
            assert reply["status"] in {"healthy", "degraded", "unhealthy"}
            assert "summary" in reply
            assert "modules" in reply["summary"]
            assert "stats" in reply["summary"]
            assert "recentMessages" not in reply["summary"]["stats"]
            assert "registry" not in reply
            assert "stats" not in reply
            assert "diagnostics" in reply
        finally:
            client.stop()


def test_node_get_health_can_include_detailed_node_state():
    with make_test_node("test_node"):
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "node.get_health",
                    "timeoutSeconds": 5,
                    "includeDetails": True,
                },
                timeout=2,
            )

            assert reply["ok"] is True
            assert "summary" in reply
            assert "registry" in reply
            assert "stats" in reply
            assert "recentMessages" in reply["stats"]
        finally:
            client.stop()


def test_node_get_health_reports_degraded_when_module_is_offline():
    with make_test_node("test_node") as node:
        module = BusInterface(
            "sensor_1",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            registered = node.registry.get("sensor_1")
            assert registered is not None
            registered.last_seen -= 10

            reply = client.send_request(
                "intrabus.node",
                {
                    "command": "node.get_health",
                    "timeoutSeconds": 5,
                },
                timeout=2,
            )

            assert reply["ok"] is True
            assert reply["status"] == "degraded"

            codes = {
                diagnostic["code"] for diagnostic in reply["diagnostics"]["diagnostics"]
            }

            assert "MODULE_OFFLINE" in codes
        finally:
            module.stop()
            client.stop()


def test_node_new_query_commands_are_supported():
    with make_test_node("test_node"):
        client = BusInterface(
            "client",
            reqrep_broker_addr="tcp://127.0.0.1:15560",
            enable_heartbeat=False,
        )

        try:
            registry_reply = client.send_request(
                "intrabus.node",
                {"command": "node.get_registry"},
                timeout=2,
            )
            stats_reply = client.send_request(
                "intrabus.node",
                {"command": "node.get_stats"},
                timeout=2,
            )
            diagnostics_reply = client.send_request(
                "intrabus.node",
                {"command": "node.get_diagnostics"},
                timeout=2,
            )

            assert registry_reply["ok"] is True
            assert "registry" in registry_reply

            assert stats_reply["ok"] is True
            assert "stats" in stats_reply

            assert diagnostics_reply["ok"] is True
            assert "diagnostics" in diagnostics_reply
        finally:
            client.stop()
