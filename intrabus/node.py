from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .brokers import CentralBroker, TopicBroker
from .bus_interface import BusInterface
from .config import INTRABUS_NODE_MODULE
from .diagnostics import DiagnosticsManager
from .registry import ModuleRegistry
from .stats import StatsCollector

logger = logging.getLogger(__name__)


@dataclass
class CommunicationNode:
    """Run the core intrabus communication infrastructure."""

    node_id: str = "local"
    topic_broker: TopicBroker = field(default_factory=TopicBroker)
    central_broker: CentralBroker = field(default_factory=CentralBroker)
    stats: StatsCollector = field(default_factory=StatsCollector)
    diagnostics: DiagnosticsManager = field(default_factory=DiagnosticsManager)
    registry: ModuleRegistry = field(init=False)
    _running: bool = field(default=False, init=False)
    _node_interface: BusInterface | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.registry = ModuleRegistry(node_id=self.node_id)

    def start(self) -> None:
        """Start the node brokers.

        Calling this multiple times is safe.
        """
        if self._running:
            return

        self.topic_broker.stats = self.stats
        self.central_broker.stats = self.stats

        self.topic_broker.start()
        self.central_broker.start()

        self._node_interface = BusInterface(
            INTRABUS_NODE_MODULE,
            pubsub_forwarder_sub_addr=self.topic_broker.sub_bind,
            pubsub_forwarder_pub_addr=self.topic_broker.pub_bind,
            reqrep_broker_addr=self.central_broker.bind,
            request_handler=self._handle_node_request,
            auto_register=False,
            enable_heartbeat=True,
            stats=self.stats,
        )

        self._running = True

        logger.info("CommunicationNode '%s' started", self.node_id)

    def stop(self) -> None:
        """Stop the node brokers.

        Calling this multiple times is safe.
        """
        if not self._running:
            return

        if self._node_interface is not None:
            self._node_interface.stop()
            self._node_interface = None

        self.topic_broker.stop()
        self.central_broker.stop()
        self._running = False

        logger.info("CommunicationNode '%s' stopped", self.node_id)

    @property
    def is_running(self) -> bool:
        """Return whether the communication node is currently running."""
        return self._running

    def _handle_node_request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle internal requests sent to the communication node."""
        command = message.get("command")

        if command == "module.heartbeat":
            return self._handle_module_heartbeat(message)

        if command == "module.register":
            return self._register_module(message)

        if command == "module.unregister":
            return self._unregister_module(message)

        if command in {"registry.get", "node.get_registry"}:
            return self._get_node_registry()

        if command == "registry.health":
            return self._get_registry_health(message)

        if command in {"stats.get", "node.get_stats"}:
            return self._get_node_stats()

        if command in {"stats.reset", "node.reset_stats"}:
            return self._reset_node_stats()

        if command in {"diagnostics.get", "node.get_diagnostics"}:
            return self._get_node_diagnostics()

        if command in {"diagnostics.clear", "node.clear_diagnostics"}:
            return self._clear_node_diagnostics()

        if command == "node.get_health":
            return self._get_node_health(message)

        return {
            "ok": False,
            "error": f"Unknown node command: {command}",
        }

    def _handle_module_heartbeat(self, message: dict[str, Any]) -> dict[str, Any]:
        module_name = message.get("moduleName")

        if not isinstance(module_name, str) or not module_name:
            return {"ok": False, "error": "moduleName is required"}

        self.registry.mark_seen(module_name)

        module = self.registry.get(module_name)

        return {
            "ok": True,
            "module": {
                "moduleName": module.module_name,
                "nodeId": module.node_id,
                "address": module.address,
                "status": module.status,
                "lastSeen": module.last_seen,
            },
        }

    def _register_module(self, message: dict[str, Any]) -> dict[str, Any]:
        module_name = message.get("moduleName")

        if not isinstance(module_name, str) or not module_name:
            return {
                "ok": False,
                "error": "moduleName is required",
            }

        capabilities = message.get("capabilities")
        metadata = message.get("metadata")

        try:
            module = self.registry.register(
                module_name,
                capabilities=capabilities if isinstance(capabilities, list) else None,
                metadata=metadata if isinstance(metadata, dict) else None,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        return {
            "ok": True,
            "module": {
                "moduleName": module.module_name,
                "nodeId": module.node_id,
                "address": module.address,
                "status": module.status,
            },
        }

    def _unregister_module(self, message: dict[str, Any]) -> dict[str, Any]:
        module_name = message.get("moduleName")

        if not isinstance(module_name, str) or not module_name:
            return {
                "ok": False,
                "error": "moduleName is required",
            }

        self.registry.unregister(module_name)

        return {
            "ok": True,
            "moduleName": module_name,
            "status": "offline",
        }

    def _get_registry_health(self, message: dict[str, Any]) -> dict[str, Any]:
        timeout_seconds = message.get("timeoutSeconds", 5.0)

        if not isinstance(timeout_seconds, int | float):
            timeout_seconds = 5.0

        stale_modules = self.registry.mark_stale_modules_offline(
            timeout_seconds=float(timeout_seconds),
        )

        return {
            "ok": True,
            "staleModules": [module.module_name for module in stale_modules],
            "registry": self.registry.to_dict(),
        }

    def _get_node_registry(self) -> dict[str, Any]:
        return {
            "ok": True,
            "nodeId": self.node_id,
            "registry": self.registry.to_dict(),
        }

    def _get_node_stats(self) -> dict[str, Any]:
        return {
            "ok": True,
            "nodeId": self.node_id,
            "stats": self.stats.to_dict(),
        }

    def _get_node_diagnostics(self) -> dict[str, Any]:
        self.diagnostics.refresh_from_runtime(
            registry=self.registry,
            stats=self.stats,
        )

        return {
            "ok": True,
            "nodeId": self.node_id,
            "diagnostics": self.diagnostics.to_dict(),
        }

    def _get_node_health(self, message: dict[str, Any]) -> dict[str, Any]:
        timeout_seconds = message.get("timeoutSeconds", 5.0)

        if not isinstance(timeout_seconds, int | float):
            timeout_seconds = 5.0

        stale_modules = self.registry.mark_stale_modules_offline(
            timeout_seconds=float(timeout_seconds),
        )

        self.diagnostics.refresh_from_runtime(
            registry=self.registry,
            stats=self.stats,
        )

        diagnostics = self.diagnostics.to_dict()
        severities = {
            diagnostic["severity"] for diagnostic in diagnostics["diagnostics"]
        }

        if "critical" in severities or "error" in severities:
            status = "unhealthy"
        elif "warning" in severities:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "ok": True,
            "nodeId": self.node_id,
            "status": status,
            "staleModules": [module.module_name for module in stale_modules],
            "registry": self.registry.to_dict(),
            "stats": self.stats.to_dict(),
            "diagnostics": diagnostics,
        }

    def _reset_node_stats(self) -> dict[str, Any]:
        self.stats.reset()
        return {
            "ok": True,
            "nodeId": self.node_id,
        }

    def _clear_node_diagnostics(self) -> dict[str, Any]:
        self.diagnostics.clear()
        return {
            "ok": True,
            "nodeId": self.node_id,
        }

    def __enter__(self) -> CommunicationNode:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.stop()
        return False
