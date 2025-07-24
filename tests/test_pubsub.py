"""Verify publish→subscribe round‑trip."""
import time
from intrabus import run_topic_broker, run_central_broker, BusInterface

def test_pubsub_roundtrip():
    # singletons make repeated starts idempotent
    run_topic_broker()
    run_central_broker()

    received = {}
    b = BusInterface("B")
    b.subscribe("t", lambda t, m: received.update(m))
    a = BusInterface("A")

    a.publish("t", {"v": 1})
    time.sleep(0.05)  # background thread dispatch

    assert received == {"v": 1}
    a.stop() 
    b.stop()