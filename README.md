# intrabus

**intrabus** is a tiny ZeroMQ‑powered message bus that brings **pub/sub events** and **request‑reply RPC** to any multi‑threaded or multi‑process Python application — with **zero external infrastructure**.

## Quick Start

Install from TestPyPI while the project is in pre‑release:

```bash
pip install --index-url https://test.pypi.org/simple/ intrabus

```python
from intrabus import BusInterface, run_topic_broker, run_central_broker

# start background brokers (for dev/testing)
run_topic_broker()
run_central_broker()

# create two modules
alice = BusInterface("Alice")
bob = BusInterface("Bob")

bob.subscribe("greetings", lambda t, m: print("Bob got:", m))

alice.publish("greetings", {"msg": "Hi Bob!"})
print(bob.send_request("Alice", {"question": "ping?"}))