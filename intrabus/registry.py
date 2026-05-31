from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ModuleInfo:
    """Runtime information about a module connected to a communication node."""

    module_name: str
    node_id: str
    status: str = "online"
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def address(self) -> str:
        """Return the future multi-node address of the module."""
        return f"{self.node_id}.{self.module_name}"


class ModuleRegistry:
    """Track modules known by a communication node."""

    def __init__(self, node_id: str = "local") -> None:
        self.node_id = node_id
        self._modules: dict[str, ModuleInfo] = {}

    def register(
        self,
        module_name: str,
        *,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModuleInfo:
        """Register a module as online.

        Raises
        ------
        ValueError
            If a module with the same name is already registered as online.
        """
        existing = self._modules.get(module_name)

        if existing and existing.status == "online":
            raise ValueError(f"Module '{module_name}' is already registered")

        info = ModuleInfo(
            module_name=module_name,
            node_id=self.node_id,
            status="online",
            capabilities=capabilities or [],
            metadata=metadata or {},
        )

        self._modules[module_name] = info
        return info

    def unregister(self, module_name: str) -> None:
        """Mark a module as offline.

        The module entry is kept so diagnostics and history can still use it.
        """
        module = self._modules.get(module_name)

        if module is None:
            return

        module.status = "offline"
        module.last_seen = time.time()

    def mark_seen(self, module_name: str) -> None:
        """Update the last-seen timestamp for a module.

        If the module is unknown, it is registered automatically with default
        metadata. This keeps the registry tolerant of older BusInterface users.
        """
        module = self._modules.get(module_name)

        if module is None:
            self.register(module_name)
            return

        module.last_seen = time.time()

        if module.status == "offline":
            module.status = "online"

    def mark_offline(self, module_name: str) -> None:
        """Mark a module as offline."""
        self.unregister(module_name)

    def mark_stale_modules_offline(self, timeout_seconds: float) -> list[ModuleInfo]:
        """Mark online modules offline if they have not been seen recently."""
        now = time.time()
        stale_modules: list[ModuleInfo] = []

        for module in self._modules.values():
            if module.status != "online":
                continue

            if now - module.last_seen > timeout_seconds:
                module.status = "offline"
                stale_modules.append(module)

        return stale_modules

    def get(self, module_name: str) -> ModuleInfo | None:
        """Return information for one module, if known."""
        return self._modules.get(module_name)

    def contains(self, module_name: str) -> bool:
        """Return whether the registry knows about a module."""
        return module_name in self._modules

    def list_modules(self) -> list[ModuleInfo]:
        """Return all known modules."""
        return list(self._modules.values())

    def list_online(self) -> list[ModuleInfo]:
        """Return modules currently marked online."""
        return [
            module for module in self._modules.values() if module.status == "online"
        ]  # noqa: E501

    def list_offline(self) -> list[ModuleInfo]:
        """Return modules currently marked offline."""
        return [
            module for module in self._modules.values() if module.status == "offline"
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the registry state."""
        return {
            "nodeId": self.node_id,
            "modules": {
                name: {
                    "moduleName": module.module_name,
                    "nodeId": module.node_id,
                    "address": module.address,
                    "status": module.status,
                    "connectedAt": module.connected_at,
                    "lastSeen": module.last_seen,
                    "capabilities": module.capabilities,
                    "metadata": module.metadata,
                }
                for name, module in self._modules.items()
            },
        }
