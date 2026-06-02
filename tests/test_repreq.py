import time

from intrabus import BusInterface, CentralBroker


def test_stale_reply_is_not_dispatched_to_request_handler():
    handled = []
    interface = BusInterface(
        "request_server",
        request_handler=lambda message: handled.append(message) or {"ok": True},
        auto_register=False,
        enable_heartbeat=False,
    )

    try:
        interface._handle_rr_frames(
            [
                b"",
                b"intrabus.node",
                b"",
                (
                    b'{"__intrabus_type":"reply","correlationId":"stale",'
                    b'"sender":"intrabus.node","ok":false}'
                ),
            ]
        )

        assert handled == []
    finally:
        interface.stop()


def test_legacy_untyped_stale_node_reply_is_not_dispatched_to_request_handler():
    handled = []
    interface = BusInterface(
        "request_server",
        request_handler=lambda message: handled.append(message) or {"ok": True},
        auto_register=False,
        enable_heartbeat=False,
    )

    try:
        interface._handle_rr_frames(
            [
                b"",
                b"intrabus.node",
                b"",
                b'{"correlationId":"stale","sender":"intrabus.node","ok":false}',
            ]
        )

        assert handled == []
    finally:
        interface.stop()


def test_request_handler_replies_are_marked_as_replies():
    broker = CentralBroker(bind="tcp://127.0.0.1:15661")
    broker.start()

    srv = None
    cli = None

    try:
        srv = BusInterface(
            "srv",
            reqrep_broker_addr="tcp://127.0.0.1:15661",
            request_handler=lambda m: {"pong": True},
            auto_register=False,
            enable_heartbeat=False,
        )
        cli = BusInterface(
            "cli",
            reqrep_broker_addr="tcp://127.0.0.1:15661",
            auto_register=False,
            enable_heartbeat=False,
        )

        time.sleep(0.1)
        reply = cli.send_request("srv", {"ping": True}, timeout=2)

        assert reply.get("pong") is True
        assert reply.get("__intrabus_type") == "reply"
    finally:
        if srv is not None:
            srv.stop()
        if cli is not None:
            cli.stop()
        broker.stop()


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
