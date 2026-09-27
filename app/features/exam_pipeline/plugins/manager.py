"""
Plugin manager.
"""

from __future__ import annotations

from .registry import PluginRegistry
from .types import PluginType


class PluginManager:

    def __init__(

        self,

        registry: PluginRegistry,

    ):

        self._registry = registry

    # -----------------------------------------------------

    def question_generator(self):

        return self._registry.get_default(

            PluginType.QUESTION_GENERATOR

        )

    def answer_evaluator(self):

        return self._registry.get_default(

            PluginType.ANSWER_EVALUATOR

        )

    def goal_generator(self):

        return self._registry.get_default(

            PluginType.GOAL_GENERATOR

        )

    def navigation_strategy(self):

        return self._registry.get_default(

            PluginType.NAVIGATION_STRATEGY

        )

    def interview_strategy(self):

        return self._registry.get_default(

            PluginType.INTERVIEW_STRATEGY

        )

    def llm(self):

        return self._registry.get_default(

            PluginType.LLM_PROVIDER

        )