"""
app/services/knowledge_service.py

Application service responsible for transforming uploaded educational
resources into a KnowledgeBase.

Responsibilities
----------------
- Coordinate the knowledge ingestion pipeline.
- Persist KnowledgeBase instances.
- Provide CRUD operations for knowledge bases.
- Delegate extraction to KnowledgeProvider and KnowledgeProcessor.

This service contains no extraction algorithms and no HTTP concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from uuid import uuid4

from ..knowledge.models import KnowledgeBase
from ..knowledge.processor import KnowledgeProcessor
from ..unit_of_work.unit_of_work import UnitOfWork


# ==========================================================
# Result DTO
# ==========================================================


@dataclass(slots=True)
class KnowledgeProcessingResult:
    """
    Result returned after successfully processing educational
    resources into a KnowledgeBase.
    """

    knowledge_base: KnowledgeBase

    processing_time: float

    statistics: dict[str, Any] = field(default_factory=dict)

    warnings: list[str] = field(default_factory=list)


# ==========================================================
# Service
# ==========================================================


class KnowledgeService:
    """
    Application service for the Knowledge layer.

    The service coordinates the ingestion workflow while delegating
    resource loading and knowledge extraction to the injected
    provider and processor.

    Dependencies
    ------------
    provider:
        Loads uploaded resources and converts them into knowledge
        documents.

    processor:
        Extracts concepts, relationships, learning outcomes,
        misconceptions, examples, topics, and related knowledge.

    uow:
        Provides persistence repositories and transaction handling.
    """

    def __init__(
        self,
        *,
        provider,
        processor: KnowledgeProcessor,
        uow: UnitOfWork,
    ) -> None:
        self._provider = provider
        self._processor = processor
        self._uow = uow

    # ==========================================================
    # Internal helpers
    # ==========================================================

    @staticmethod
    def _generate_id() -> str:
        """
        Generate a unique KnowledgeBase identifier.
        """

        return str(uuid4())
####################TEMP
    def _get(
            self,
            knowledge_id: str,
    ) -> KnowledgeBase | None:

        knowledge = self._uow.knowledge.get(
            knowledge_id
        )

        print(
            "DEBUG KnowledgeService._get",
            "requested_id=", knowledge_id,
            "repository=", id(self._uow.knowledge),
            "found=", knowledge is not None,
        )

        if knowledge is not None:
            print(
                "DEBUG found knowledge:",
                knowledge.id,
                knowledge.title,
            )

        return knowledge
#################
    def _get_o(
        self,
        knowledge_id: str,
    ) -> KnowledgeBase | None:
        """
        Retrieve a KnowledgeBase by identifier.

        This method intentionally returns None when the resource
        does not exist.
        """

        if not knowledge_id:
            return None

        return self._uow.knowledge.get(
            knowledge_id
        )

    def _require(
        self,
        knowledge_id: str,
    ) -> KnowledgeBase:
        """
        Retrieve a KnowledgeBase or raise ValueError.
        """

        knowledge = self._get(
            knowledge_id
        )

        if knowledge is None:
            raise ValueError(
                f"Knowledge base '{knowledge_id}' does not exist."
            )

        return knowledge
#################TEMP
    def _save(
            self,
            knowledge_base: KnowledgeBase,
    ) -> None:

        print(
            "DEBUG KnowledgeService._save",
            "knowledge_id=", knowledge_base.id,
            "repository=", id(self._uow.knowledge),
        )

        with self._uow:
            self._uow.knowledge.add(
                knowledge_base
            )

            self._uow.commit()
    def save(self, knowledge_base: KnowledgeBase) -> None:
        """
        Public method to persist or update a KnowledgeBase.
        """
        with self._uow:
            self._uow.knowledge.add(knowledge_base)
            self._uow.commit()

    def _save_o(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:
        """
        Persist a new KnowledgeBase.
        """

        with self._uow:
            self._uow.knowledge.add(
                knowledge_base
            )
            self._uow.commit()

    def _update(
        self,
        knowledge_base: KnowledgeBase,
    ) -> None:
        """
        Persist changes to an existing KnowledgeBase.
        """

        with self._uow:
            self._uow.knowledge.update(
                knowledge_base
            )
            self._uow.commit()

    def _statistics(
        self,
        knowledge_base: KnowledgeBase,
    ) -> dict[str, Any]:
        """
        Compute summary statistics for a KnowledgeBase.
        """

        return {
            "documents": len(
                knowledge_base.documents
            ),
            "topics": len(
                knowledge_base.topics
            ),
            "concepts": len(
                knowledge_base.concepts
            ),
            "relationships": len(
                knowledge_base.relationships
            ),
            "learning_outcomes": len(
                knowledge_base.learning_outcomes
            ),
            "examples": len(
                knowledge_base.examples
            ),
            "misconceptions": len(
                knowledge_base.misconceptions
            ),
        }

    @staticmethod
    def _elapsed_seconds(
        started_at: datetime,
    ) -> float:
        """
        Return elapsed processing time in seconds.
        """

        return (
            datetime.utcnow() - started_at
        ).total_seconds()

    # ==========================================================
    # Knowledge ingestion
    # ==========================================================

    def ingest_resources(
        self,
        resources: Iterable[Any],
        *,
        title: str,
        description: str = "",
        language: str = "en",
        domain: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeProcessingResult:
        """
        Build and persist a KnowledgeBase from uploaded resources.

        Workflow
        --------
        1. Load resources through the provider.
        2. Construct the KnowledgeBase.
        3. Process and enrich the KnowledgeBase.
        4. Persist the aggregate.
        5. Return processing statistics.

        Raises
        ------
        RuntimeError
            If resource loading or knowledge processing fails.
        """

        started_at = datetime.utcnow()

        warnings: list[str] = []

        # ------------------------------------------------------
        # Load resources
        # ------------------------------------------------------

        try:
            documents = self._provider.load(
                resources
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to load uploaded resources."
            ) from exc

        # ------------------------------------------------------
        # Construct aggregate
        # ------------------------------------------------------

        knowledge_base = KnowledgeBase(
            id=self._generate_id(),
            title=title,
            description=description,
            domain=domain,
            documents=documents,
            metadata=dict(
                metadata or {}
            ),
        )

        # Preserve the requested language without changing
        # the existing metadata contract.
        if "language" not in knowledge_base.metadata:
            knowledge_base.metadata["language"] = language

        # ------------------------------------------------------
        # Process knowledge
        # ------------------------------------------------------

        try:
            self._processor.process(
                knowledge_base
            )
        except Exception as exc:
            raise RuntimeError(
                "Knowledge extraction failed."
            ) from exc

        # ------------------------------------------------------
        # Persist
        # ------------------------------------------------------

        self._save(
            knowledge_base
        )

        # ------------------------------------------------------
        # Result
        # ------------------------------------------------------

        return KnowledgeProcessingResult(
            knowledge_base=knowledge_base,
            processing_time=self._elapsed_seconds(
                started_at
            ),
            statistics=self._statistics(
                knowledge_base
            ),
            warnings=warnings,
        )

    # ==========================================================
    # CRUD
    # ==========================================================

    def get_knowledge_base(
        self,
        knowledge_id: str,
    ) -> KnowledgeBase | None:
        """
        Retrieve a KnowledgeBase.

        Returns None when the requested identifier does not exist.
        """

        return self._get(
            knowledge_id
        )

    def list_knowledge_bases(
        self,
    ) -> list[KnowledgeBase]:
        """
        Return all persisted KnowledgeBases.
        """

        return list(
            self._uow.knowledge.list()
        )

    def delete_knowledge_base(
        self,
        knowledge_id: str,
    ) -> None:
        """
        Delete a KnowledgeBase.

        Raises
        ------
        ValueError
            If the KnowledgeBase does not exist.
        """

        self._require(
            knowledge_id
        )

        with self._uow:
            self._uow.knowledge.delete(
                knowledge_id
            )
            self._uow.commit()

    def exists(
        self,
        knowledge_id: str,
    ) -> bool:
        """
        Return True when the KnowledgeBase exists.
        """

        if not knowledge_id:
            return False

        return bool(
            self._uow.knowledge.exists(
                knowledge_id
            )
        )

    # ==========================================================
    # Metadata
    # ==========================================================

    def update_metadata(
        self,
        knowledge_id: str,
        metadata: dict[str, Any],
    ) -> KnowledgeBase:
        """
        Update KnowledgeBase metadata.
        """

        knowledge = self._require(
            knowledge_id
        )

        knowledge.metadata.update(
            metadata
        )

        self._update(
            knowledge
        )

        return knowledge

    def rename(
        self,
        knowledge_id: str,
        *,
        title: str,
        description: str | None = None,
    ) -> KnowledgeBase:
        """
        Update the title and optionally the description.
        """

        knowledge = self._require(
            knowledge_id
        )

        knowledge.title = title

        if description is not None:
            knowledge.description = description

        self._update(
            knowledge
        )

        return knowledge

    # ==========================================================
    # Documents
    # ==========================================================

    def add_documents(
        self,
        knowledge_id: str,
        resources: Iterable[Any],
    ) -> KnowledgeBase:
        """
        Add documents to an existing KnowledgeBase.

        The new documents are processed together with the existing
        knowledge aggregate.
        """

        knowledge = self._require(
            knowledge_id
        )

        try:
            documents = self._provider.load(
                resources
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to load uploaded resources."
            ) from exc

        knowledge.documents.extend(
            documents
        )

        try:
            self._processor.process(
                knowledge
            )
        except Exception as exc:
            raise RuntimeError(
                "Knowledge extraction failed."
            ) from exc

        self._update(
            knowledge
        )

        return knowledge

    def clear(
        self,
    ) -> None:
        """
        Remove all persisted KnowledgeBases.

        Intended primarily for testing and administrative cleanup.
        """

        with self._uow:
            self._uow.knowledge.clear()
            self._uow.commit()

    # ==========================================================
    # Search
    # ==========================================================

    def search(
        self,
        *,
        knowledge_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[Any]:
        """
        Search within a KnowledgeBase.

        If the repository provides a native search implementation,
        it is delegated to that implementation.

        Otherwise an empty result is returned.
        """

        self._require(
            knowledge_id
        )

        if not query:
            return []

        top_k = max(
            1,
            int(top_k),
        )

        repository = self._uow.knowledge

        search_method = getattr(
            repository,
            "search",
            None,
        )

        if search_method is None:
            return []

        return list(
            search_method(
                knowledge_id=knowledge_id,
                query=query,
                top_k=top_k,
            )
        )

    # ==========================================================
    # Validation
    # ==========================================================

    def validate(
        self,
        knowledge_id: str,
    ) -> bool:
        """
        Validate that a KnowledgeBase exists and contains
        at least one document.
        """

        knowledge = self._get(
            knowledge_id
        )

        if knowledge is None:
            return False

        return bool(
            knowledge.documents
        )

    # ==========================================================
    # Statistics
    # ==========================================================

    def statistics(
        self,
        knowledge_id: str,
    ) -> dict[str, Any]:
        """
        Return summary statistics for a KnowledgeBase.
        """

        knowledge = self._require(
            knowledge_id
        )

        return self._statistics(
            knowledge
        )

    # ==========================================================
    # Export
    # ==========================================================

    def export(
        self,
        knowledge_id: str,
    ) -> KnowledgeBase:
        """
        Return the complete KnowledgeBase aggregate.
        """

        return self._require(
            knowledge_id
        )

    # ==========================================================
    # Health
    # ==========================================================

    def health(
        self,
    ) -> dict[str, Any]:
        """
        Return diagnostic information about the service.
        """

        return {
            "service": type(self).__name__,
            "repository": type(
                self._uow.knowledge
            ).__name__,
            "processor": type(
                self._processor
            ).__name__,
            "provider": type(
                self._provider
            ).__name__,
        }