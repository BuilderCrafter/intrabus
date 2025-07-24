"""Verify request→reply round‑trip."""
from intrabus import run_topic_broker, run_central_broker, BusInterface

def test_reqrep_roundtrip():
    run_topic_broker() 
    run_central_broker()

    def echo(msg):
        return {"echo": msg}

    a = BusInterface("A", request_handler=echo)
    b = BusInterface("B")

    reply = b.send_request("A", {"ping": True}, timeout=1)
    assert reply.get("echo", {}).get("ping") is True

    a.stop()
    b.stop()