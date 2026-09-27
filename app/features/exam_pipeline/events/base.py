"""
Base event types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class DomainEvent:
    """
    Base class for every domain event.
    """

    event_id: str = field(
        default_factory=lambda: str(uuid4())
    )

    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )