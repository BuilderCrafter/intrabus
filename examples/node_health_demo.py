"""Show registry, stats, diagnostics, and node health commands."""

import time

from intrabus import BusInterface, CommunicationNode


def main() -> None:
    """Run a small node-health query demo."""
    with CommunicationNode("health-demo"):
        worker = BusInterface("worker", enable_heartbeat=False)
        client = BusInterface("client", enable_heartbeat=False)

        try:
            registry = client.send_request(
                "intrabus.node",
                {"command": "node.get_registry"},
                timeout=2,
            )
            print("registered modules:", list(registry["registry"]["modules"]))

            # Let the worker become stale according to a tiny health timeout.
            time.sleep(0.2)

            health = client.send_request(
                "intrabus.node",
                {
                    "command": "node.get_health",
                    "timeoutSeconds": 0.1,
                },
                timeout=2,
            )

            print("status:", health["status"])
            print("diagnostics:", health["diagnostics"]["diagnostics"])
        finally:
            worker.stop()
            client.stop()


if __name__ == "__main__":
    main()
