"""
Logging decorators.
"""

from __future__ import annotations

import functools
import time

from .logger import FrameworkLogger

logger = FrameworkLogger()


def log_execution(name: str):

    def decorator(function):

        @functools.wraps(function)
        def wrapper(*args, **kwargs):

            logger.info(f"{name} started")

            start = time.perf_counter()

            try:

                result = function(*args, **kwargs)

                elapsed = time.perf_counter() - start

                logger.info(
                    f"{name} completed",
                    elapsed=elapsed,
                )

                return result

            except Exception:

                logger.exception(
                    f"{name} failed"
                )

                raise

        return wrapper

    return decorator