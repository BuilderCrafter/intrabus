"""Minimal demo of intrabus usage (sync)."""
from intrabus import run_topic_broker, run_central_broker, BusInterface

# start brokers once per process
run_topic_broker()
run_central_broker()

# two modules
with BusInterface("A") as a, BusInterface("B") as b:
    # pub/sub
    b.subscribe("hello", lambda t, m: print("B got", m))
    a.publish("hello", {"msg": "hi"})

    # request/reply
    def echo(msg):
        print("A saw", msg)
        return {"echo": msg}
    a.request_handler = echo

    print("RPC reply:", b.send_request("A", {"ping": True}))