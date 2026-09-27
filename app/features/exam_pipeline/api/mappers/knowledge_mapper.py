"""
api/mappers/knowledge_mapper.py

Maps Knowledge domain models to API DTOs.
"""

from __future__ import annotations
from ..schemas.knowledge import (
    KnowledgeResponse,
    KnowledgeSummary,
    KnowledgeSearchResponse,
    SearchResult,
)


class KnowledgeMapper:
    """
    Converts KnowledgeModel objects into API schemas.
    """

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    @staticmethod
    def to_summary(model) -> KnowledgeSummary:

        return KnowledgeSummary(

            id=model.id,

            title=model.title,

            description=model.description,

            resource_count=len(model.resources),

            concept_count=len(model.graph.nodes),

            relationship_count=len(model.graph.edges),

            language=model.language,

            metadata=model.metadata,
        )

    # ---------------------------------------------------------
    # Full Response
    # ---------------------------------------------------------

    @staticmethod
    def to_response(model) -> KnowledgeResponse:

        return KnowledgeResponse(

            id=model.id,

            title=model.title,

            description=model.description,

            language=model.language,

            resources=[
                resource.filename
                for resource in model.resources
            ],

            concepts=[
                concept.name
                for concept in model.graph.nodes.values()
            ],

            metadata=model.metadata,
        )

    # ---------------------------------------------------------
    # List
    # ---------------------------------------------------------

    @classmethod
    def to_summary_list(
        cls,
        models,
    ) -> list[KnowledgeSummary]:

        return [
            cls.to_summary(model)
            for model in models
        ]

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    @staticmethod
    def to_search_response(
        query: str,
        results,
    ) -> KnowledgeSearchResponse:

        return KnowledgeSearchResponse(

            query=query,

            results=[

                SearchResult(

                    text=result.text,

                    score=result.score,

                    source=getattr(
                        result,
                        "source",
                        None,
                    ),

                    metadata=getattr(
                        result,
                        "metadata",
                        {},
                    ),

                )

                for result
                in results
            ],
        )