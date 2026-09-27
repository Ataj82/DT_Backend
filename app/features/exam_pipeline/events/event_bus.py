"""
Simple synchronous event bus.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable
from typing import Type

from .base import DomainEvent


class EventBus:

    def __init__(self):

        self._handlers = defaultdict(list)

    # ---------------------------------------------------------

    def subscribe(

        self,

        event_type: Type[DomainEvent],

        handler: Callable,

    ):

        self._handlers[event_type].append(
            handler
        )

    # ---------------------------------------------------------

    def publish(
        self,
        event: DomainEvent,
    ):

        handlers = self._handlers.get(
            type(event),
            [],
        )

        for handler in handlers:

            handler(event)