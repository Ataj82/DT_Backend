"""
app/knowledge/models.py

Core domain models for the Knowledge Layer.

These models represent the processed educational knowledge extracted
from uploaded resources.

Workflow

KnowledgeProvider
        ↓
Document
        ↓
KnowledgeProcessor
        ↓
KnowledgeBase
        ↓
GoalGenerator
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .document import Document


# ==========================================================
# Enumerations
# ==========================================================

class RelationshipType(str, Enum):
    REQUIRES = "requires"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    EXTENDS = "extends"
    DEPENDS_ON = "depends_on"


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


# ==========================================================
# Topic
# ==========================================================

class Topic(BaseModel):
    id: str

    title: str

    summary: str | None = None

    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )


# ==========================================================
# Concept
# ==========================================================

class Concept(BaseModel):
    id: str

    name: str

    definition: str | None = None

    aliases: list[str] = Field(
        default_factory=list
    )

    topic_id: str | None = None

    difficulty: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    references: list[str] = Field(
        default_factory=list
    )


# ==========================================================
# Relationship
# ==========================================================

class Relationship(BaseModel):
    source_id: str

    target_id: str

    relationship: RelationshipType

    weight: float = Field(
        default=1.0,
        ge=0.0,
    )


# ==========================================================
# Learning Outcome
# ==========================================================

class LearningOutcome(BaseModel):
    id: str

    description: str

    bloom_level: BloomLevel

    concept_ids: list[str] = Field(
        default_factory=list
    )


# ==========================================================
# Example
# ==========================================================

class Example(BaseModel):
    id: str

    concept_id: str

    text: str

    source_document: str | None = None


# ==========================================================
# Misconception
# ==========================================================

class Misconception(BaseModel):
    id: str

    concept_id: str

    misconception: str

    correction: str


# ==========================================================
# Knowledge Base
# ==========================================================

class KnowledgeBase(BaseModel):
    """
    Root aggregate of the Knowledge domain.
    """

    id: str

    title: str

    description: str | None = None

    domain: str | None = None

    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )

    #
    # Uploaded source documents
    #
    documents: list[Document] = Field(
        default_factory=list
    )

    #
    # Extracted knowledge
    #
    topics: list[Topic] = Field(
        default_factory=list
    )

    concepts: list[Concept] = Field(
        default_factory=list
    )

    relationships: list[Relationship] = Field(
        default_factory=list
    )

    learning_outcomes: list[LearningOutcome] = Field(
        default_factory=list
    )

    examples: list[Example] = Field(
        default_factory=list
    )

    misconceptions: list[Misconception] = Field(
        default_factory=list
    )

    #
    # Optional generated graph
    #
    graph: Any | None = None

    #
    # Arbitrary metadata
    #
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )