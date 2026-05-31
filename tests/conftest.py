"""Shared test cleanup for ZeroMQ broker singletons."""

import time

import pytest

from intrabus import stop_central_broker, stop_topic_broker


@pytest.fixture(autouse=True)
def cleanup_broker_singletons():
    """Ensure process-wide broker helpers do not leak between tests."""
    yield
    stop_topic_broker()
    stop_central_broker()
    time.sleep(0.02)
