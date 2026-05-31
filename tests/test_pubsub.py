import threading
import time

from intrabus import BusInterface, TopicBroker


def test_pubsub_roundtrip():
    broker = TopicBroker(
        sub_bind="tcp://127.0.0.1:15658",
        pub_bind="tcp://127.0.0.1:15659",
    )
    broker.start()

    flag = threading.Event()
    a = None
    b = None

    try:
        b = BusInterface(
            "B",
            pubsub_forwarder_sub_addr="tcp://127.0.0.1:15658",
            pubsub_forwarder_pub_addr="tcp://127.0.0.1:15659",
            auto_register=False,
            enable_heartbeat=False,
        )
        b.subscribe("t", lambda *_: flag.set())

        a = BusInterface(
            "A",
            pubsub_forwarder_sub_addr="tcp://127.0.0.1:15658",
            pubsub_forwarder_pub_addr="tcp://127.0.0.1:15659",
            auto_register=False,
            enable_heartbeat=False,
        )
        time.sleep(0.1)  # allow SUB handshake locally

        a.publish("t", {"v": 1})
        time.sleep(0.1)  # give background thread time to deliver

        assert flag.is_set(), "subscriber did not receive message"
    finally:
        if a is not None:
            a.stop()
        if b is not None:
            b.stop()
        broker.stop()
