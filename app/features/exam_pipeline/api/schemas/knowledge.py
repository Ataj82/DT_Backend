"""
app/api/schemas/knowledge.py

API schemas for knowledge management.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from uuid import uuid4
from .common import APIModel


# ==========================================================
# Uploaded Resource
# ==========================================================

class KnowledgeResource(APIModel):
    """
    One uploaded educational resource.
    """

    filename: str

    content: str

    content_type: str = "text/plain"

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


# ==========================================================
# Create Knowledge Base
# ==========================================================

class CreateKnowledgeRequest(APIModel):
    """
    Request for creating a knowledge base.
    """

    title: str

    description: str | None = None

    resources: list[KnowledgeResource]

    # Optional teacher-provided KB language. If omitted, the backend
    # detects the dominant source language and stores the result.
    language: str | None = Field(
        default=None,
        pattern=r"^(en|fa)$",
        description="Optional knowledge-base language override: en or fa.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


# ==========================================================
# Summary
# ==========================================================

class KnowledgeSummary(APIModel):

    id: str

    title: str

    description: str | None = None

    resource_count: int

    concept_count: int

    relationship_count: int

    language: str

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


# ==========================================================
# Details
# ==========================================================

class KnowledgeResponse(APIModel):

    id: str

    title: str

    description: str | None = None

    language: str

    resources: list[str]

    concepts: list[str]

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


# ==========================================================
# Search
# ==========================================================

class KnowledgeSearchRequest(APIModel):

    knowledge_id: str

    query: str

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class SearchResult(APIModel):

    text: str

    score: float

    source: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class KnowledgeSearchResponse(APIModel):

    query: str

    results: list[SearchResult]