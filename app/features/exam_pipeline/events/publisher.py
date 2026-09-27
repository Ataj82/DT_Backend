"""
Framework event publisher.
"""

from __future__ import annotations

from .event_bus import EventBus


class EventPublisher:

    def __init__(
        self,
        bus: EventBus,
    ):
        self._bus = bus

    def publish(self, event):

        self._bus.publish(event)