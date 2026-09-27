"""
Plugin registry.
"""

from __future__ import annotations

from collections import defaultdict

from .base import Plugin
from .types import PluginType


class PluginRegistry:

    def __init__(self):

        self._plugins: dict[
            PluginType,
            dict[str, Plugin],
        ] = defaultdict(dict)

    # -----------------------------------------------------

    def register(
        self,
        plugin: Plugin,
    ):

        plugin.initialize()

        self._plugins[
            plugin.plugin_type
        ][plugin.name] = plugin

    # -----------------------------------------------------

    def get(

        self,

        plugin_type: PluginType,

        name: str,

    ) -> Plugin:

        return self._plugins[
            plugin_type
        ][name]

    # -----------------------------------------------------

    def get_default(

        self,

        plugin_type: PluginType,

    ) -> Plugin:

        plugins = self._plugins[
            plugin_type
        ]

        if not plugins:

            raise ValueError(
                f"No plugin registered for {plugin_type}"
            )

        return next(iter(plugins.values()))

    # -----------------------------------------------------

    def list(

        self,

        plugin_type: PluginType,

    ) -> list[str]:

        return list(

            self._plugins[
                plugin_type
            ].keys()

        )