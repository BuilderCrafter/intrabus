# intrabus

**intrabus** is a lightweight, general-purpose ZeroMQ communication node for Python applications.

It gives independent modules a simple way to communicate over:

- **publish/subscribe events**
- **request/reply messages**
- **module registration**
- **heartbeats and liveness tracking**
- **runtime statistics**
- **diagnostics**
- **node health queries**

The goal is to keep setup simple: install the library, start a `CommunicationNode`, connect modules with `BusInterface`, and communicate.

```bash
pip install intrabus
```

> Current release target: `0.2.3`
>
> `intrabus` is still alpha software. The public API is usable, but the project may still evolve before `1.0`.

---

## Why intrabus?

Use intrabus when you want multiple Python components to communicate inside one machine or between local processes without deploying external infrastructure such as Redis, RabbitMQ, Kafka, or HTTP services.

Typical use cases:

- test automation systems
- modular desktop applications
- robotics or hardware-control tools
- local monitoring/control systems
- plugin-like Python applications
- prototypes that may later grow into distributed systems

`intrabus` is not intended to replace large production message brokers. It is designed to be small, embeddable, and easy to reason about.

---

## Quick start

```python
from intrabus import BusInterface, CommunicationNode


def handle_request(message: dict) -> dict:
    return {
        "pong": True,
        "received": message,
    }


with CommunicationNode("local"):
    server = BusInterface("server", request_handler=handle_request)
    client = BusInterface("client")

    reply = client.send_request("server", {"ping": True}, timeout=2)
    print(reply)

    health = client.send_request(
        "intrabus.node",
        {"command": "node.get_health"},
        timeout=2,
    )
    print(health["status"])

    server.stop()
    client.stop()
```

---

## Core concepts

### CommunicationNode

`CommunicationNode` owns the core intrabus runtime:

- `TopicBroker` for pub/sub traffic
- `CentralBroker` for request/reply traffic
- `ModuleRegistry` for known modules
- `StatsCollector` for runtime metrics
- `DiagnosticsManager` for runtime diagnostics

Most users should start here:

```python
from intrabus import CommunicationNode

with CommunicationNode("local") as node:
    print(node.is_running)
```

### BusInterface

`BusInterface` is what application modules use to communicate.

```python
from intrabus import BusInterface

module = BusInterface("sensor")
```

A `BusInterface` can:

- publish events
- subscribe to events
- send requests
- handle incoming requests
- auto-register with the local node
- send heartbeats to the local node

### Module registry

When a module starts, it can automatically register with the node:

```python
worker = BusInterface("worker")
```

The node tracks:

- module name
- node ID
- status: `online` or `offline`
- connected time
- last seen time
- capabilities
- metadata

### Heartbeats and stale detection

By default, modules send periodic heartbeats to the node.

The node can mark modules offline when they stop sending heartbeats:

```python
reply = client.send_request(
    "intrabus.node",
    {
        "command": "node.get_health",
        "timeoutSeconds": 5,
    },
)
```

---

## Publish/subscribe

```python
from intrabus import BusInterface, CommunicationNode


with CommunicationNode():
    publisher = BusInterface("publisher")
    subscriber = BusInterface("subscriber")

    def on_temperature(topic: str, message: dict) -> None:
        print(topic, message)

    subscriber.subscribe("temperature", on_temperature)
    publisher.publish("temperature", {"value": 23.5})

    publisher.stop()
    subscriber.stop()
```

---

## Request/reply

```python
from intrabus import BusInterface, CommunicationNode


def echo(message: dict) -> dict:
    return {"echo": message}


with CommunicationNode():
    server = BusInterface("server", request_handler=echo)
    client = BusInterface("client")

    reply = client.send_request("server", {"hello": "world"}, timeout=2)
    print(reply)

    server.stop()
    client.stop()
```

`BusInterface` reserves a few request/reply payload fields for protocol
metadata:

- `correlationId`
- `sender`
- `__intrabus_type`

The `__intrabus_type` marker is added automatically as `"request"` or
`"reply"`. It prevents late replies from being treated as new application
requests after node restarts or transient disconnects.

---

## Node management commands

The internal node service is available at:

```text
intrabus.node
```

Send requests to it with `BusInterface.send_request()`.

### `node.get_registry`

Returns the current module registry.

```python
client.send_request("intrabus.node", {"command": "node.get_registry"})
```

### `node.get_stats`

Returns current runtime statistics.

```python
client.send_request("intrabus.node", {"command": "node.get_stats"})
```

### `node.get_diagnostics`

Returns current diagnostics derived from registry and stats.

```python
client.send_request("intrabus.node", {"command": "node.get_diagnostics"})
```

### `node.get_health`

Returns a compact node health payload suitable for monitoring:

```python
client.send_request(
    "intrabus.node",
    {
        "command": "node.get_health",
        "timeoutSeconds": 5,
    },
)
```

The health response contains:

```python
{
    "ok": True,
    "nodeId": "local",
    "status": "healthy",  # healthy | degraded | unhealthy
    "staleModules": [],
    "summary": {
        "modules": {
            "total": 2,
            "online": 2,
            "offline": 0,
        },
        "stats": {
            "totalMessages": 10,
            "totalRequests": 5,
            "totalReplies": 4,
            "totalTimeouts": 0,
            "totalErrors": 0,
            "totalEvents": 1,
            "totalDeliveryFailures": 0,
        },
        "diagnostics": {
            "count": 0,
            "severityCounts": {},
        },
    },
    "diagnostics": {...},
}
```

To include the full registry and raw stats payload, including recent events and
recent messages, pass `includeDetails`:

```python
client.send_request(
    "intrabus.node",
    {
        "command": "node.get_health",
        "includeDetails": True,
    },
)
```

### `node.reset_stats`

Clears runtime statistics.

```python
client.send_request("intrabus.node", {"command": "node.reset_stats"})
```

### `node.clear_diagnostics`

Clears currently stored diagnostics.

```python
client.send_request("intrabus.node", {"command": "node.clear_diagnostics"})
```

---

## Backward-compatible node commands

The following older command names are still supported:

| Older command | Preferred command |
|---|---|
| `registry.get` | `node.get_registry` |
| `stats.get` | `node.get_stats` |
| `diagnostics.get` | `node.get_diagnostics` |
| `stats.reset` | `node.reset_stats` |
| `diagnostics.clear` | `node.clear_diagnostics` |

Internal module lifecycle commands are also supported:

- `module.register`
- `module.unregister`
- `module.heartbeat`
- `registry.health`

Most application code should use the `node.*` commands.

---

## Runtime statistics

`StatsCollector` tracks bounded in-memory application traffic statistics:

- total messages
- requests
- replies
- events
- timeouts
- errors
- delivery failures
- latency samples
- average latency
- max latency
- per-module stats
- per-topic stats
- recent events
- recent message metadata

User-facing traffic stats intentionally exclude internal node-management
traffic, including module registration, module heartbeat, registry polling,
health checks, diagnostics polling, and stats polling. This keeps monitoring
clients and web dashboards from inflating application message totals.

Request/reply latency is measured centrally by the request/reply broker using
matching application `correlationId` values. This means `node.get_stats`
reports application RTT even when individual modules create `BusInterface`
instances without passing a `StatsCollector`. Missing targets, timed-out
requests without replies, and internal node-management commands do not create
latency samples.

Recent messages are bounded and do **not** include full payloads by default. This avoids unbounded RAM growth and reduces the risk of accidentally storing sensitive data.

---

## Diagnostics

`DiagnosticsManager` currently derives diagnostics from registry and stats.
Repeated recent stats events are grouped into higher-level diagnostics to keep
monitoring output readable.

Supported diagnostic codes:

| Code | Meaning |
|---|---|
| `MODULE_OFFLINE` | A registered module is offline |
| `REQUEST_TIMEOUT` | A request timed out |
| `HANDLER_ERROR` | A request handler raised an exception |
| `DELIVERY_FAILURE` | A message could not be delivered by the broker |

Diagnostic severities:

- `info`
- `warning`
- `error`
- `critical`

`node.get_health` maps diagnostics to node status:

| Status | Meaning |
|---|---|
| `healthy` | No warnings or errors |
| `degraded` | At least one warning |
| `unhealthy` | At least one error or critical diagnostic |

---

## MessageEnvelope

`MessageEnvelope` is a dataclass for future-compatible standardized messages.

It includes fields for future multi-node support:

- `messageId`
- `correlationId`
- `sender`
- `target`
- `topic`
- `sourceNode`
- `targetNode`
- `ttl`
- `hopPath`
- `payload`

The current brokers still use lightweight JSON payloads internally, but `MessageEnvelope` is available as the standard message shape for higher-level integrations.

---

## Advanced: manual brokers

Most users should use `CommunicationNode`.

For low-level control, you can still start brokers manually:

```python
from intrabus import run_central_broker, run_topic_broker

run_topic_broker()
run_central_broker()
```

And stop singleton brokers:

```python
from intrabus import stop_central_broker, stop_topic_broker

stop_topic_broker()
stop_central_broker()
```

This is mainly useful for simple scripts and compatibility with older examples.

---

## Development

Install development dependencies:

```bash
uv sync --dev
```

Run tests:

```bash
uv run pytest -q
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Format code:

```bash
uv run ruff format .
```

Build the package:

```bash
uv run python -m build
```

Check distributions:

```bash
uv run twine check dist/*
```

---

## Roadmap

Planned future work:

- event/message sinks for streaming to external consumers
- demo project using this package
- monitoring dashboard as a separate project
- richer diagnostics
- multi-node routing
- optional dashboard/websocket integrations

The library itself will stay focused on being a general-purpose communication node.

---

## License

MIT
