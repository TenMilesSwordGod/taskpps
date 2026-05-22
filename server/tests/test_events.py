import pytest
from taskpps.events.bus import EventBus, get_event_bus, SIGNAL_PIPELINE_STARTED, SIGNAL_TASK_STARTED, SIGNAL_TASK_FINISHED, SIGNAL_RUN_COMPLETED, SIGNAL_RUN_CANCELLED


def test_event_bus_create():
    bus = EventBus()
    assert bus is not None


def test_event_bus_singleton():
    bus1 = get_event_bus()
    bus2 = get_event_bus()
    assert bus1 is bus2


def test_event_bus_on_emit():
    bus = EventBus()
    received = []

    def handler(sender, **kwargs):
        received.append(kwargs)

    bus.on("test_event", handler)
    bus.emit("test_event", sender=None, data="hello")
    assert len(received) == 1
    assert received[0]["data"] == "hello"


def test_event_bus_off():
    bus = EventBus()
    received = []

    def handler(sender, **kwargs):
        received.append(True)

    bus.on("test_event", handler)
    bus.emit("test_event", sender=None)
    assert len(received) == 1

    bus.off("test_event", handler)
    bus.emit("test_event", sender=None)
    assert len(received) == 1


def test_signal_constants():
    assert SIGNAL_PIPELINE_STARTED == "pipeline_started"
    assert SIGNAL_TASK_STARTED == "task_started"
    assert SIGNAL_TASK_FINISHED == "task_finished"
    assert SIGNAL_RUN_COMPLETED == "run_completed"
    assert SIGNAL_RUN_CANCELLED == "run_cancelled"
