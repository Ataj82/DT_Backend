"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from .types import PluginType


class Plugin(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def plugin_type(self) -> PluginType:
        ...

    @abstractmethod
    def initialize(self) -> None:
        """
        Called when the plugin is registered.
        """