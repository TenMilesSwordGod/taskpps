from __future__ import annotations

from taskpps.events.bus import (
    SIGNAL_PIPELINE_STARTED,
    SIGNAL_RUN_CANCELLED,
    SIGNAL_RUN_COMPLETED,
    SIGNAL_TASK_FINISHED,
    SIGNAL_TASK_STARTED,
    EventBus,
    get_event_bus,
)


class TestEventBus:
    @pytest.mark.zentao("TC-S0724", domain="server/events", priority="P0")
    def test_singleton_instance(self):
        bus1 = EventBus.get_instance()
        bus2 = EventBus.get_instance()
        assert bus1 is bus2

    @pytest.mark.zentao("TC-S0725", domain="server/events", priority="P2")
    def test_get_event_bus_function(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    @pytest.mark.zentao("TC-S0726", domain="server/events", priority="P1")
    def test_get_signal_creates_new(self):
        bus = EventBus()
        signal = bus._get_signal("test_event")
        assert signal is not None
        assert "test_event" in bus._signals

    @pytest.mark.zentao("TC-S0727", domain="server/events", priority="P1")
    def test_get_signal_reuses_existing(self):
        bus = EventBus()
        signal1 = bus._get_signal("test_event")
        signal2 = bus._get_signal("test_event")
        assert signal1 is signal2

    @pytest.mark.zentao("TC-S0728", domain="server/events", priority="P0")
    def test_on_and_emit(self):
        bus = EventBus()
        received = []

        def handler(sender, **kwargs):
            received.append((sender, kwargs))

        bus.on("test_event", handler)
        bus.emit("test_event", self, data=42)

        assert len(received) == 1
        assert received[0][0] == self
        assert received[0][1]["data"] == 42

    @pytest.mark.zentao("TC-S0729", domain="server/events", priority="P2")
    def test_on_multiple_handlers(self):
        bus = EventBus()
        count1 = 0
        count2 = 0

        def handler1(*args, **kwargs):
            nonlocal count1
            count1 += 1

        def handler2(*args, **kwargs):
            nonlocal count2
            count2 += 1

        bus.on("test", handler1)
        bus.on("test", handler2)
        bus.emit("test")

        assert count1 == 1
        assert count2 == 1

    @pytest.mark.zentao("TC-S0730", domain="server/events", priority="P2")
    def test_off_remove_handler(self):
        bus = EventBus()
        count = 0

        def handler(*args, **kwargs):
            nonlocal count
            count += 1

        bus.on("test", handler)
        bus.emit("test")
        assert count == 1

        bus.off("test", handler)
        bus.emit("test")
        assert count == 1

    @pytest.mark.zentao("TC-S0731", domain="server/events", priority="P2")
    def test_off_nonexistent_event(self):
        bus = EventBus()

        def handler():
            pass

        bus.off("nonexistent", handler)

    @pytest.mark.zentao("TC-S0732", domain="server/events", priority="P2")
    def test_off_handler_not_in_event(self):
        bus = EventBus()
        count = 0

        def handler1(sender, **kwargs):
            nonlocal count
            count += 1

        def handler2(sender, **kwargs):
            pass

        bus.on("test", handler1)
        bus.off("test", handler2)
        bus.emit("test")
        assert count == 1

    @pytest.mark.zentao("TC-S0733", domain="server/events", priority="P2")
    def test_emit_without_sender(self):
        bus = EventBus()
        received_sender = None

        def handler(sender, **kwargs):
            nonlocal received_sender
            received_sender = sender

        bus.on("test", handler)
        bus.emit("test")
        assert received_sender is None

    @pytest.mark.zentao("TC-S0734", domain="server/events", priority="P2")
    def test_emit_without_kwargs(self):
        bus = EventBus()
        received = None

        def handler(sender, **kwargs):
            nonlocal received
            received = kwargs

        bus.on("test", handler)
        bus.emit("test")
        assert received == {}

    @pytest.mark.zentao("TC-S0735", domain="server/events", priority="P1")
    def test_signal_constants_defined(self):
        assert SIGNAL_PIPELINE_STARTED == "pipeline_started"
        assert SIGNAL_TASK_STARTED == "task_started"
        assert SIGNAL_TASK_FINISHED == "task_finished"
        assert SIGNAL_RUN_COMPLETED == "run_completed"
        assert SIGNAL_RUN_CANCELLED == "run_cancelled"

    @pytest.mark.zentao("TC-S0736", domain="server/events", priority="P2")
    def test_multiple_events_independent(self):
        bus = EventBus()
        event1_fired = False
        event2_fired = False

        def h1(*args, **kwargs):
            nonlocal event1_fired
            event1_fired = True

        def h2(*args, **kwargs):
            nonlocal event2_fired
            event2_fired = True

        bus.on("event1", h1)
        bus.on("event2", h2)
        bus.emit("event1")

        assert event1_fired is True
        assert event2_fired is False

    @pytest.mark.zentao("TC-S0737", domain="server/events", priority="P2")
    def test_empty_event_name(self):
        bus = EventBus()
        signal = bus._get_signal("")
        assert signal is not None
        assert "" in bus._signals

    @pytest.mark.zentao("TC-S0738", domain="server/events", priority="P2")
    def test_special_char_event_name(self):
        bus = EventBus()
        received = False

        def handler(*args, **kwargs):
            nonlocal received
            received = True

        bus.on("event-with-dashes_underscores", handler)
        bus.emit("event-with-dashes_underscores")
        assert received is True

    @pytest.mark.zentao("TC-S0739", domain="server/events", priority="P2")
    def test_multiple_emit_same_event(self):
        bus = EventBus()
        count = 0

        def handler(*args, **kwargs):
            nonlocal count
            count += 1

        bus.on("test", handler)
        for _ in range(100):
            bus.emit("test")
        assert count == 100


class TestEventBusBoundary:
    @pytest.mark.zentao("TC-S0740", domain="server/events", priority="P2")
    def test_large_number_of_events(self):
        bus = EventBus()
        counts = {}

        for i in range(100):

            def make_handler(idx):
                def handler(*args, **kwargs):
                    counts[idx] = counts.get(idx, 0) + 1

                return handler

            bus.on(f"event_{i}", make_handler(i))

        for i in range(100):
            bus.emit(f"event_{i}")

        assert all(count == 1 for count in counts.values())
        assert len(bus._signals) == 100

    @pytest.mark.zentao("TC-S0741", domain="server/events", priority="P2")
    def test_same_handler_multiple_events(self):
        bus = EventBus()
        total_count = 0

        def handler(*args, **kwargs):
            nonlocal total_count
            total_count += 1

        for i in range(10):
            bus.on(f"event_{i}", handler)

        for i in range(10):
            bus.emit(f"event_{i}")

        assert total_count == 10

    @pytest.mark.zentao("TC-S0742", domain="server/events", priority="P2")
    def test_emit_with_large_payload(self):
        bus = EventBus()
        received_data = None

        def handler(sender, data, **kwargs):
            nonlocal received_data
            received_data = data

        large_data = {"key": "value" * 1000}
        bus.on("test", handler)
        bus.emit("test", self, data=large_data)

        assert received_data == large_data

    @pytest.mark.zentao("TC-S0743", domain="server/events", priority="P2")
    def test_concurrent_emit(self):
        import threading

        bus = EventBus()
        counter = 0
        lock = threading.Lock()

        def handler(*args, **kwargs):
            nonlocal counter
            with lock:
                counter += 1

        bus.on("test", handler)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: bus.emit("test"))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        assert counter == 10

    @pytest.mark.zentao("TC-S0744", domain="server/events", priority="P1")
    def test_init_empty_signals(self):
        bus = EventBus()
        assert bus._signals == {}

