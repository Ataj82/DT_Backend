"""
Registers framework default plugins.
"""

from ..plugins.registry import PluginRegistry

# Import your existing implementations
from ..navigation.sequential_navigation import SequentialNavigation
from ..strategy.goal_based_strategy import GoalBasedInterviewStrategy


def register_defaults(
    registry: PluginRegistry,
):

    registry.register(
        SequentialNavigation()
    )

    registry.register(
        GoalBasedInterviewStrategy()
    )