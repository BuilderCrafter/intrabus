import pytest

from intrabus import ModuleRegistry


def test_register_module():
    registry = ModuleRegistry(node_id="test_node")

    module = registry.register("sensor_1")

    assert module.module_name == "sensor_1"
    assert module.node_id == "test_node"
    assert module.address == "test_node.sensor_1"
    assert module.status == "online"
    assert registry.contains("sensor_1") is True


def test_register_duplicate_online_module_raises_error():
    registry = ModuleRegistry(node_id="test_node")

    registry.register("sensor_1")

    with pytest.raises(ValueError, match="already registered"):
        registry.register("sensor_1")


def test_unregister_marks_module_offline():
    registry = ModuleRegistry(node_id="test_node")
    registry.register("sensor_1")

    registry.unregister("sensor_1")

    module = registry.get("sensor_1")
    assert module is not None
    assert module.status == "offline"


def test_unregister_unknown_module_does_nothing():
    registry = ModuleRegistry(node_id="test_node")

    registry.unregister("unknown")

    assert registry.list_modules() == []


def test_mark_seen_updates_existing_module():
    registry = ModuleRegistry(node_id="test_node")
    module = registry.register("sensor_1")
    previous_last_seen = module.last_seen

    registry.mark_seen("sensor_1")

    updated = registry.get("sensor_1")
    assert updated is not None
    assert updated.last_seen >= previous_last_seen
    assert updated.status == "online"


def test_mark_seen_registers_unknown_module():
    registry = ModuleRegistry(node_id="test_node")

    registry.mark_seen("sensor_1")

    module = registry.get("sensor_1")
    assert module is not None
    assert module.module_name == "sensor_1"
    assert module.status == "online"


def test_mark_seen_brings_offline_module_online():
    registry = ModuleRegistry(node_id="test_node")
    registry.register("sensor_1")
    registry.unregister("sensor_1")

    registry.mark_seen("sensor_1")

    module = registry.get("sensor_1")
    assert module is not None
    assert module.status == "online"


def test_lists_online_and_offline_modules():
    registry = ModuleRegistry(node_id="test_node")
    registry.register("online_module")
    registry.register("offline_module")
    registry.unregister("offline_module")

    online = registry.list_online()
    offline = registry.list_offline()

    assert [module.module_name for module in online] == ["online_module"]
    assert [module.module_name for module in offline] == ["offline_module"]


def test_registry_serializes_to_dict():
    registry = ModuleRegistry(node_id="test_node")
    registry.register(
        "sensor_1",
        capabilities=["pubsub", "reqrep"],
        metadata={"role": "sensor"},
    )

    data = registry.to_dict()

    assert data["nodeId"] == "test_node"
    assert data["modules"]["sensor_1"]["moduleName"] == "sensor_1"
    assert data["modules"]["sensor_1"]["address"] == "test_node.sensor_1"
    assert data["modules"]["sensor_1"]["status"] == "online"
    assert data["modules"]["sensor_1"]["capabilities"] == ["pubsub", "reqrep"]
    assert data["modules"]["sensor_1"]["metadata"] == {"role": "sensor"}


def test_registry_marks_stale_modules_offline():
    registry = ModuleRegistry(node_id="test_node")
    module = registry.register("sensor_1")

    module.last_seen -= 10

    stale = registry.mark_stale_modules_offline(timeout_seconds=5)

    assert [module.module_name for module in stale] == ["sensor_1"]
    assert registry.get("sensor_1").status == "offline"
