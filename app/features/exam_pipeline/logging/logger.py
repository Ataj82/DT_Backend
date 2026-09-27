"""
Framework logging utilities.
"""

from __future__ import annotations

import logging
import sys


class FrameworkLogger:
    """
    Central logger used throughout the framework.
    """

    def __init__(
        self,
        name: str = "assessment-framework",
        level: int = logging.INFO,
    ):

        self._logger = logging.getLogger(name)

        if not self._logger.handlers:

            handler = logging.StreamHandler(sys.stdout)

            formatter = logging.Formatter(

                fmt=(
                    "%(asctime)s | "
                    "%(levelname)s | "
                    "%(name)s | "
                    "%(message)s"
                ),

                datefmt="%Y-%m-%d %H:%M:%S",

            )

            handler.setFormatter(formatter)

            self._logger.addHandler(handler)

            self._logger.setLevel(level)

            self._logger.propagate = False

    # ---------------------------------------------------------
    # Convenience methods
    # ---------------------------------------------------------

    def debug(self, message: str, **extra):
        self._logger.debug(message, extra=extra)

    def info(self, message: str, **extra):
        self._logger.info(message, extra=extra)

    def warning(self, message: str, **extra):
        self._logger.warning(message, extra=extra)

    def error(self, message: str, **extra):
        self._logger.error(message, extra=extra)

    def exception(self, message: str, **extra):
        self._logger.exception(message, extra=extra)