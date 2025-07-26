import time
from intrabus import run_topic_broker, run_central_broker, BusInterface


def test_reqrep_roundtrip():
    run_topic_broker()
    run_central_broker()

    srv = BusInterface("srv", request_handler=lambda m: {"pong": True})
    cli = BusInterface("cli")

    time.sleep(0.1)          # allow DEALER handshake locally
    reply = cli.send_request("srv", {"ping": True}, timeout=2)

    assert reply.get("pong") is True

    srv.stop()
    cli.stop()
    