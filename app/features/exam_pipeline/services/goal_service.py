"""
app/services/goal_service.py

Application service responsible for GoalModel lifecycle.

Responsibilities
----------------
- Generate GoalModels from KnowledgeBases
- Persist GoalModels
- Retrieve GoalModels
- Review GoalModels
- Delete GoalModels

Generation logic lives inside GoalGenerator.
"""

from __future__ import annotations

from ..goals.generator import GoalGenerator
from ..goals.models import GoalModel, GoalStatus
from ..language.resolver import detect_knowledge_language, normalize_language
from ..unit_of_work.unit_of_work import UnitOfWork


class GoalService:
    """
    Coordinates goal generation and persistence.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        generator: GoalGenerator | None = None,
    ):
        self.uow = uow
        self.generator = generator or GoalGenerator()

    # ==========================================================
    # Generate
    # ==========================================================

    def generate(
        self,
        *,
        knowledge_id: str,
        max_goals: int | None = None,
        include_optional: bool = True,
    ) -> GoalModel:
        """
        Generate assessment goals from a KnowledgeBase.
        """

        with self.uow:

            kb = self.uow.knowledge.get(knowledge_id)

            if kb is None:
                raise ValueError(
                    f"Knowledge base '{knowledge_id}' not found."
                )

            if kb.graph is None:
                raise ValueError(
                    "Knowledge base graph has not been generated."
                )

            language = normalize_language((getattr(kb, "metadata", {}) or {}).get("language"))
            if language is None:
                language = detect_knowledge_language(kb)
            goal_model = self.generator.generate(
                graph=kb.graph,
                max_goals=max_goals,
                include_optional=include_optional,
                language=language,
            )

            self.uow.goals.save(goal_model)

            self.uow.commit()

            return goal_model

    # ==========================================================
    # Retrieve
    # ==========================================================

    def get(
        self,
        goal_model_id: str,
    ) -> GoalModel | None:

        with self.uow:
            return self.uow.goals.get(goal_model_id)

    def list(self) -> list[GoalModel]:

        with self.uow:
            return list(self.uow.goals.list())

    # ==========================================================
    # Save
    # ==========================================================

    def save(
        self,
        goal_model: GoalModel,
    ) -> GoalModel:

        with self.uow:

            self.uow.goals.save(goal_model)

            self.uow.commit()

            return goal_model

    # ==========================================================
    # Review
    # ==========================================================

    def review(
        self,
        *,
        goal_model_id: str,
        approved_goal_ids: list[str],
    ) -> GoalModel:
        """
        Mark approved goals.
        """

        with self.uow:

            goal_model = self.uow.goals.get(goal_model_id)

            if goal_model is None:
                raise ValueError(
                    "Goal model not found."
                )

            for goal in goal_model.goals:

                if goal.id in approved_goal_ids:
                    goal.status = GoalStatus.APPROVED
                else:
                    goal.status = GoalStatus.DISABLED

            self.uow.goals.save(goal_model)

            self.uow.commit()

            return goal_model

    # ==========================================================
    # Delete
    # ==========================================================

    def delete(
        self,
        goal_model_id: str,
    ) -> None:

        with self.uow:

            self.uow.goals.delete(goal_model_id)

            self.uow.commit()