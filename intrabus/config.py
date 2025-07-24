"""Default socket addresses; override via environment variables if desired."""
import os

FORWARDER_SUB_ADDR = os.getenv("INTRABUS_SUB_ADDR", "tcp://127.0.0.1:5558")
FORWARDER_PUB_ADDR = os.getenv("INTRABUS_PUB_ADDR", "tcp://127.0.0.1:5559")
REPREQ_DEALER_ADDR = os.getenv("INTRABUS_REP_ADDR", "tcp://127.0.0.1:5560")