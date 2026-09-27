"""
app/services/service_container.py

Dependency container for the interview application.

The ServiceContainer owns all long-lived services used by the
application. It acts as the application's composition root.

Responsibilities
----------------
- Hold singleton services
- Provide dependency lookup
- Avoid constructor explosion
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ServiceContainer:
    """
    Registry of application services.

    This class intentionally contains no business logic.
    """

    # ---------------------------------------------------------
    # Infrastructure
    # ---------------------------------------------------------

    config: Any

    metrics: Any

    llm: Any

    knowledge_base: Any

    memory: Any

    # ---------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------

    rubric_engine: Any

    judge: Any

    scorer: Any

    confidence_tracker: Any

    # ---------------------------------------------------------
    # Assessment
    # ---------------------------------------------------------

    coverage_engine: Any

    information_gain_planner: Any

    evidence_planner: Any

    outcome_manager: Any

    progress_reasoner: Any

    assessment_engine: Any

    evaluation_service: Any

    # ---------------------------------------------------------
    # Question Generation
    # ---------------------------------------------------------

    question_generator: Any