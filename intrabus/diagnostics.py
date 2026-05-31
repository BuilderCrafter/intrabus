from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .registry import ModuleRegistry
from .stats import StatsCollector


@dataclass(slots=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)
    module: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
            "module": self.module,
            "metadata": self.metadata,
        }


class DiagnosticsManager:
    """Collect and expose runtime diagnostics for a CommunicationNode."""

    def __init__(self, max_diagnostics: int = 1000) -> None:
        self._diagnostics: deque[Diagnostic] = deque(maxlen=max_diagnostics)

    def add(
        self,
        *,
        code: str,
        severity: str,
        message: str,
        module: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Diagnostic:
        diagnostic = Diagnostic(
            code=code,
            severity=severity,
            message=message,
            module=module,
            metadata=metadata or {},
        )
        self._diagnostics.append(diagnostic)
        return diagnostic

    def clear(self) -> None:
        self._diagnostics.clear()

    def get_all(self) -> list[Diagnostic]:
        return list(self._diagnostics)

    def to_dict(self) -> dict[str, Any]:
        diagnostics = [diagnostic.to_dict() for diagnostic in self._diagnostics]

        return {
            "count": len(diagnostics),
            "diagnostics": diagnostics,
        }

    def refresh_from_runtime(
        self,
        *,
        registry: ModuleRegistry,
        stats: StatsCollector,
    ) -> None:
        """Refresh derived diagnostics from registry and stats state.

        This keeps Diagnostics v1 simple: it derives current problems from
        registry/stats instead of requiring every component to emit diagnostics
        directly.
        """
        self.clear()

        self._collect_module_offline(registry)
        self._collect_stats_diagnostics(stats)

    def _collect_module_offline(self, registry: ModuleRegistry) -> None:
        for module in registry.list_offline():
            self.add(
                code="MODULE_OFFLINE",
                severity="warning",
                module=module.module_name,
                message=f"Module '{module.module_name}' is offline",
                metadata={
                    "nodeId": module.node_id,
                    "lastSeen": module.last_seen,
                    "connectedAt": module.connected_at,
                },
            )

    def _collect_stats_diagnostics(self, stats: StatsCollector) -> None:
        data = stats.to_dict()

        for event in data["recentEvents"]:
            event_type = event.get("type")

            if event_type == "request.timeout":
                module = event.get("module")
                target = event.get("target")

                self.add(
                    code="REQUEST_TIMEOUT",
                    severity="warning",
                    module=module,
                    message=f"Request from '{module}' to '{target}' timed out",
                    metadata={
                        "target": target,
                        "correlationId": event.get("correlationId"),
                    },
                )

            elif event_type == "error":
                module = event.get("module")
                error = event.get("metadata", {}).get("error")

                self.add(
                    code="HANDLER_ERROR",
                    severity="error",
                    module=module,
                    message=f"Module '{module}' handler raised an error",
                    metadata={
                        "error": error,
                        "correlationId": event.get("correlationId"),
                    },
                )

            elif event_type == "delivery.failure":
                sender = event.get("sender")
                target = event.get("target")
                reason = event.get("metadata", {}).get("reason")

                self.add(
                    code="DELIVERY_FAILURE",
                    severity="error",
                    module=sender,
                    message=(
                        f"Message from '{sender}' to '{target}' could not be delivered"
                    ),
                    metadata={
                        "target": target,
                        "reason": reason,
                        "correlationId": event.get("correlationId"),
                    },
                )
