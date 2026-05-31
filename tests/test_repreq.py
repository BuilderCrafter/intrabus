import time

from intrabus import BusInterface, CentralBroker


def test_reqrep_roundtrip():
    broker = CentralBroker(bind="tcp://127.0.0.1:15660")
    broker.start()

    srv = None
    cli = None

    try:
        srv = BusInterface(
            "srv",
            reqrep_broker_addr="tcp://127.0.0.1:15660",
            request_handler=lambda m: {"pong": True},
            auto_register=False,
            enable_heartbeat=False,
        )
        cli = BusInterface(
            "cli",
            reqrep_broker_addr="tcp://127.0.0.1:15660",
            auto_register=False,
            enable_heartbeat=False,
        )

        time.sleep(0.1)  # allow DEALER handshake locally
        reply = cli.send_request("srv", {"ping": True}, timeout=2)

        assert reply.get("pong") is True
    finally:
        if srv is not None:
            srv.stop()
        if cli is not None:
            cli.stop()
        broker.stop()
