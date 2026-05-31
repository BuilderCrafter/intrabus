# Changelog

All notable changes to **intrabus** will be documented here.

The project follows semantic versioning while it is in alpha. Public APIs may still evolve before `1.0.0`.

## [0.2.0] - 2026-05-31

### Added

- Added `CommunicationNode` as the high-level runtime entry point.
- Added `MessageEnvelope` dataclass for standardized, future-compatible message structure.
- Added `ModuleRegistry` with module metadata, status, capabilities, and timestamps.
- Added message-based module registration through `intrabus.node`.
- Added automatic module registration from `BusInterface`.
- Added automatic module unregister on `BusInterface.stop()`.
- Added heartbeat support from modules to the communication node.
- Added stale module detection through registry health checks.
- Added `StatsCollector` with bounded in-memory stats.
- Added recent event and recent message metadata tracking.
- Added request latency tracking.
- Added timeout, error, and delivery-failure stats.
- Added `DiagnosticsManager`.
- Added diagnostics for:
  - `MODULE_OFFLINE`
  - `REQUEST_TIMEOUT`
  - `HANDLER_ERROR`
  - `DELIVERY_FAILURE`
- Added node management commands:
  - `node.get_registry`
  - `node.get_stats`
  - `node.get_diagnostics`
  - `node.get_health`
  - `node.reset_stats`
  - `node.clear_diagnostics`
- Added compatibility aliases for older registry/stats/diagnostics commands.
- Added singleton broker stop helpers:
  - `stop_topic_broker()`
  - `stop_central_broker()`

### Changed

- Improved broker lifecycle handling.
- Replaced blocking broker loops with poller-based loops.
- Improved `BusInterface` subscriber shutdown behavior.
- Updated the primary usage model from manual brokers to `CommunicationNode`.
- Updated examples and documentation for the communication-node architecture.
- Modernized package metadata for the `0.2.0` release.

### Fixed

- Fixed broker shutdown issues that could leave ports bound after tests.
- Fixed subscriber thread shutdown hangs.
- Fixed singleton broker restart behavior.
- Fixed internal node interface address handling for custom broker ports.
- Fixed stats initialization ordering during auto-registration.

## [0.1.0] - 2025-07-24

### Added

- Added synchronous single-host `TopicBroker`.
- Added synchronous `CentralBroker`.
- Added thread-safe `BusInterface` with `publish`, `subscribe`, and `send_request`.
- Added environment-overridable default addresses.
- Added context-manager support for `BusInterface`.
- Added initial examples and unit tests for pub/sub and request/reply patterns.
