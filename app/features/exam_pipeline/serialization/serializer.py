"""
serialization/serializer.py

Base serializer interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Serializer(ABC):
    """
    Generic object serializer.
    """

    @abstractmethod
    def serialize(
        self,
        obj: Any,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def deserialize(
        self,
        data: dict,
    ) -> Any:
        raise NotImplementedError