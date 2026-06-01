from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .registry import ModuleRegistry
from .stats import StatsCollector

MAX_DIAGNOSTIC_CORRELATION_IDS = 10


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
        severity_counts: dict[str, int] = {}

        for diagnostic in diagnostics:
            severity = diagnostic["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            "count": len(diagnostics),
            "severityCounts": severity_counts,
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
        timeouts: dict[tuple[Any, ...], dict[str, Any]] = {}
        handler_errors: dict[tuple[Any, ...], dict[str, Any]] = {}
        delivery_failures: dict[tuple[Any, ...], dict[str, Any]] = {}

        for event in data["recentEvents"]:
            event_type = event.get("type")

            if event_type == "request.timeout":
                module = event.get("module")
                target = event.get("target")
                key = (module, target)
                self._update_event_group(timeouts, key, event)

            elif event_type == "error":
                module = event.get("module")
                error = event.get("metadata", {}).get("error")
                key = (module, error)
                self._update_event_group(handler_errors, key, event)

            elif event_type == "delivery.failure":
                sender = event.get("sender")
                target = event.get("target")
                reason = event.get("metadata", {}).get("reason")
                key = (sender, target, reason)
                self._update_event_group(delivery_failures, key, event)

        self._add_timeout_diagnostics(timeouts)
        self._add_handler_error_diagnostics(handler_errors)
        self._add_delivery_failure_diagnostics(delivery_failures)

    @staticmethod
    def _update_event_group(
        groups: dict[tuple[Any, ...], dict[str, Any]],
        key: tuple[Any, ...],
        event: dict[str, Any],
    ) -> None:
        timestamp = event.get("timestamp")
        correlation_id = event.get("correlationId")
        group = groups.setdefault(
            key,
            {
                "count": 0,
                "firstSeen": timestamp,
                "lastSeen": timestamp,
                "correlationIds": [],
                "omittedCorrelationIds": 0,
            },
        )

        group["count"] += 1

        if timestamp is not None:
            if group["firstSeen"] is None or timestamp < group["firstSeen"]:
                group["firstSeen"] = timestamp
            if group["lastSeen"] is None or timestamp > group["lastSeen"]:
                group["lastSeen"] = timestamp

        if correlation_id is None:
            return

        if len(group["correlationIds"]) < MAX_DIAGNOSTIC_CORRELATION_IDS:
            group["correlationIds"].append(correlation_id)
        else:
            group["omittedCorrelationIds"] += 1

    def _add_timeout_diagnostics(
        self,
        groups: dict[tuple[Any, ...], dict[str, Any]],
    ) -> None:
        for (module, target), group in groups.items():
            count = group["count"]
            message = (
                f"{count} requests from '{module}' to '{target}' timed out"
                if count > 1
                else f"Request from '{module}' to '{target}' timed out"
            )

            self.add(
                code="REQUEST_TIMEOUT",
                severity="warning",
                module=module,
                message=message,
                metadata={
                    "target": target,
                    **group,
                },
            )

    def _add_handler_error_diagnostics(
        self,
        groups: dict[tuple[Any, ...], dict[str, Any]],
    ) -> None:
        for (module, error), group in groups.items():
            count = group["count"]
            message = (
                f"Module '{module}' handler raised {count} errors"
                if count > 1
                else f"Module '{module}' handler raised an error"
            )

            self.add(
                code="HANDLER_ERROR",
                severity="error",
                module=module,
                message=message,
                metadata={
                    "error": error,
                    **group,
                },
            )

    def _add_delivery_failure_diagnostics(
        self,
        groups: dict[tuple[Any, ...], dict[str, Any]],
    ) -> None:
        for (sender, target, reason), group in groups.items():
            count = group["count"]
            message = (
                f"{count} messages from '{sender}' to '{target}' could not be delivered"
                if count > 1
                else f"Message from '{sender}' to '{target}' could not be delivered"
            )

            self.add(
                code="DELIVERY_FAILURE",
                severity="error",
                module=sender,
                message=message,
                metadata={
                    "target": target,
                    "reason": reason,
                    **group,
                },
            )
