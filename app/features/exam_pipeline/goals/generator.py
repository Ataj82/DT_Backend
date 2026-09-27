"""
app/goals/generator.py

Transforms a KnowledgeGraph into a GoalModel.

The GoalGenerator performs assessment planning only.
It does NOT generate interview questions.

Workflow

KnowledgeGraph
        │
        ▼
GoalGenerator
        ▼
GoalModel
"""

from __future__ import annotations

from uuid import uuid4

from .models import (
    Goal,
    GoalIndicator,
    GoalModel,
    GoalStatus,
    IndicatorType,
)

from ..knowledge.graph import (
    KnowledgeGraph,
    NodeType,
)

from ..knowledge.models import BloomLevel


class GoalGenerator:
    """
    Generates assessment goals from a KnowledgeGraph.

    Current strategy
    ----------------
    • One assessment goal per concept.
    • Bloom level inferred from graph connectivity.
    • Indicators derived from concepts.
    • Future versions may use NLP/LLMs while keeping
      this public interface unchanged.
    """

    # ==========================================================
    # Public API
    # ==========================================================

    def generate(
            self,
            *,
            graph: KnowledgeGraph,
            max_goals: int | None = None,
            include_optional: bool = True,
    ) -> GoalModel:
        """
        Generate a complete GoalModel.

        Parameters
        ----------
        graph:
            Knowledge graph describing the learning domain.

        Returns
        -------
        GoalModel
        """

        goals: list[Goal] = []

        concept_nodes = [
            node
            for node in graph.nodes
            if node.type == NodeType.CONCEPT
        ]

        for node in concept_nodes:

            goal = self._build_goal(
                node=node,
                graph=graph,
            )

            goals.append(goal)

        if max_goals is not None:
            goals = goals[:max_goals]

        return GoalModel(
            knowledge_base_id=graph.knowledge_base_id,
            goals=goals,
            generated_by=self.__class__.__name__,
        )

    # ==========================================================
    # Goal Construction
    # ==========================================================

    def _build_goal(
        self,
        *,
        node,
        graph: KnowledgeGraph,
    ) -> Goal:

        bloom = self._estimate_bloom_level(
            node.id,
            graph,
        )

        indicator = GoalIndicator(

            id=str(uuid4()),

            name=node.label,

            indicator_type=IndicatorType.CONCEPT,

            description=node.description,

            required=True,

            weight=1.0,
        )

        return Goal(

            id=str(uuid4()),

            title=f"Demonstrate understanding of {node.label}",

            description=node.description
            or f"Assess understanding of {node.label}.",

            bloom_level=bloom,

            importance=1.0,

            difficulty=self._estimate_difficulty(
                node.id,
                graph,
            ),

            estimated_questions=self._estimate_question_count(
                node.id,
                graph,
            ),

            indicators=[indicator],

            prerequisite_goal_ids=[],

            related_concept_ids=[node.id],

            status=GoalStatus.GENERATED,
        )

    # ==========================================================
    # Bloom Level
    # ==========================================================

    def _estimate_bloom_level(
        self,
        concept_id: str,
        graph: KnowledgeGraph,
    ) -> BloomLevel:
        """
        Estimate Bloom level from graph connectivity.

        This heuristic can later be replaced by an NLP
        classifier or LLM.
        """

        degree = len(
            graph.reverse_adjacency.get(
                concept_id,
                [],
            )
        ) + len(
            graph.adjacency.get(
                concept_id,
                [],
            )
        )

        if degree <= 1:
            return BloomLevel.REMEMBER

        if degree <= 3:
            return BloomLevel.UNDERSTAND

        if degree <= 5:
            return BloomLevel.APPLY

        if degree <= 8:
            return BloomLevel.ANALYZE

        return BloomLevel.EVALUATE

    # ==========================================================
    # Difficulty
    # ==========================================================

    def _estimate_difficulty(
        self,
        concept_id: str,
        graph: KnowledgeGraph,
    ) -> float:
        """
        Estimate assessment difficulty.

        More connected concepts are usually more central
        and therefore deserve slightly higher difficulty.
        """

        degree = len(
            graph.reverse_adjacency.get(
                concept_id,
                [],
            )
        ) + len(
            graph.adjacency.get(
                concept_id,
                [],
            )
        )

        difficulty = 0.3 + degree * 0.08

        return min(
            1.0,
            round(difficulty, 2),
        )

    # ==========================================================
    # Estimated Question Count
    # ==========================================================

    def _estimate_question_count(
        self,
        concept_id: str,
        graph: KnowledgeGraph,
    ) -> int:
        """
        Estimate interview effort.

        Central concepts deserve more interview questions.
        """

        degree = len(
            graph.reverse_adjacency.get(
                concept_id,
                [],
            )
        ) + len(
            graph.adjacency.get(
                concept_id,
                [],
            )
        )

        return max(
            1,
            min(
                5,
                1 + degree // 2,
            ),
        )