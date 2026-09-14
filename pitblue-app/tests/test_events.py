import asyncio

from pitblue_app.events import ApplicationEvents


def test_event_bus_fans_out_structured_application_event():
    async def scenario():  # type: ignore[no-untyped-def]
        events = ApplicationEvents()
        async with events.subscribe() as queue:
            published = await events.publish("cook.updated", {"cookId": "cook_1"})
            received = await queue.get()
        return published, received

    published, received = asyncio.run(scenario())
    assert received == published
    assert published["type"] == "cook.updated"
    assert published["eventId"]
    assert published["occurredAt"]


def test_event_bus_bounds_slow_subscriber_queue():
    async def scenario():  # type: ignore[no-untyped-def]
        events = ApplicationEvents()
        async with events.subscribe() as queue:
            for number in range(101):
                await events.publish("measurement.updated", {"number": number})
            return queue.qsize(), (await queue.get())["data"]["number"]

    size, oldest = asyncio.run(scenario())
    assert size == 100
    assert oldest == 1


def test_sse_stream_formats_named_event():
    async def scenario() -> str:
        events = ApplicationEvents()
        stream = events.stream()
        waiting = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await events.publish("alert.triggered", {"alertId": "alert_1"})
        try:
            return await waiting
        finally:
            await stream.aclose()

    frame = asyncio.run(scenario())
    assert "event: alert.triggered" in frame
    assert '"alertId":"alert_1"' in frame


def test_sse_stream_can_be_scoped_to_one_cook():
    async def scenario() -> str:
        events = ApplicationEvents()
        stream = events.stream(lambda event: event["data"].get("cookId") == "allowed")
        waiting = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await events.publish("cook_event.created", {"cookId": "other"})
        await events.publish("cook_event.created", {"cookId": "allowed"})
        try:
            return await waiting
        finally:
            await stream.aclose()

    frame = asyncio.run(scenario())
    assert '"cookId":"allowed"' in frame
    assert '"cookId":"other"' not in frame
