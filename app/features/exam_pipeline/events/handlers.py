"""
Default event handlers.
"""

from __future__ import annotations

from ..logging import logger


def logging_handler(event):

    logger.info(

        f"Event: {event.__class__.__name__}",

        event=event,
    )