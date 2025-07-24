import time
import threading
from intrabus import run_topic_broker, run_central_broker, BusInterface


def test_pubsub_roundtrip():
    # start brokers once (idempotent)
    run_topic_broker()
    run_central_broker()

    flag = threading.Event()
    b = BusInterface("B")
    b.subscribe("t", lambda *_: flag.set())

    a = BusInterface("A")
    time.sleep(0.1)          # allow SUB handshake locally

    a.publish("t", {"v": 1})
    time.sleep(0.1)          # give background thread time to deliver

    assert flag.is_set(), "subscriber did not receive message"

    a.stop()
    b.stop()