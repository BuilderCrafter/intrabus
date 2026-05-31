"""Minimal intrabus demo using CommunicationNode."""

import time

from intrabus import BusInterface, CommunicationNode


def main() -> None:
    """Run a small pub/sub + request/reply demo."""

    def echo_handler(message: dict) -> dict:
        print("server received:", message)
        return {"echo": message}

    with CommunicationNode("demo"):
        publisher = BusInterface("publisher")
        subscriber = BusInterface("subscriber")
        server = BusInterface("server", request_handler=echo_handler)
        client = BusInterface("client")

        try:
            subscriber.subscribe(
                "demo.events",
                lambda topic, message: print(f"subscriber received {topic}: {message}"),
            )

            # Give the SUB socket a moment to subscribe before the first publish.
            time.sleep(0.1)

            publisher.publish("demo.events", {"message": "hello from pub/sub"})

            reply = client.send_request("server", {"ping": True}, timeout=2)
            print("request/reply response:", reply)

            health = client.send_request(
                "intrabus.node",
                {"command": "node.get_health"},
                timeout=2,
            )
            print("node status:", health["status"])
        finally:
            publisher.stop()
            subscriber.stop()
            server.stop()
            client.stop()


if __name__ == "__main__":
    main()
