from intrabus import (
    run_central_broker,
    run_topic_broker,
    stop_central_broker,
    stop_topic_broker,
)


def test_topic_broker_singleton_can_be_stopped_and_restarted():
    broker_1 = run_topic_broker(restart=True)
    broker_2 = run_topic_broker()

    assert broker_1 is broker_2

    stop_topic_broker()

    broker_3 = run_topic_broker()
    assert broker_3 is not broker_1

    stop_topic_broker()


def test_central_broker_singleton_can_be_stopped_and_restarted():
    broker_1 = run_central_broker(restart=True)
    broker_2 = run_central_broker()

    assert broker_1 is broker_2

    stop_central_broker()

    broker_3 = run_central_broker()
    assert broker_3 is not broker_1

    stop_central_broker()
