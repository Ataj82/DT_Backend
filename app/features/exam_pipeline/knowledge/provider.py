"""
app/knowledge/provider.py

Loads uploaded educational resources into normalized Document
objects that can be consumed by the KnowledgeProcessor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .document import Document


class KnowledgeProvider:
    """
    Converts arbitrary uploaded resources into Document objects.

    Supported inputs
    ----------------
    - API KnowledgeResource
    - raw text
    - pathlib.Path
    - file-like objects
    """

    # ======================================================
    # Public API
    # ======================================================

    def load(
        self,
        resources: Iterable[Any],
    ) -> list[Document]:

        return [
            self._load_one(resource)
            for resource in resources
        ]

    # -----------------------------------------------------

    def get_documents(
        self,
        resources: Iterable[Any],
    ) -> list[Document]:

        return self.load(resources)

    # -----------------------------------------------------

    def get_metadata(
        self,
        resources: Iterable[Any],
    ) -> dict[str, Any]:

        resources = list(resources)

        return {
            "resource_count": len(resources),
        }

    # ======================================================
    # Internal helpers
    # ======================================================

    def _load_one(
        self,
        resource: Any,
    ) -> Document:

        #
        # API KnowledgeResource
        #

        if (
            hasattr(resource, "filename")
            and hasattr(resource, "content")
        ):

            return Document(
                id=str(uuid4()),
                filename=resource.filename,
                content=resource.content,
                metadata=dict(
                    getattr(
                        resource,
                        "metadata",
                        {},
                    )
                ),
                language=getattr(
                    resource,
                    "language",
                    "en",
                ),
            )

        #
        # Raw text
        #

        if isinstance(resource, str):

            return Document(
                id=str(uuid4()),
                filename="text",
                content=resource,
            )

        #
        # pathlib.Path
        #

        if isinstance(resource, Path):

            return Document(
                id=str(uuid4()),
                filename=resource.name,
                content=resource.read_text(
                    encoding="utf-8"
                ),
                metadata={
                    "path": str(resource),
                },
            )

        #
        # File-like object
        #

        if hasattr(resource, "read"):

            content = resource.read()

            if isinstance(content, bytes):

                content = content.decode(
                    "utf-8",
                    errors="ignore",
                )

            return Document(
                id=str(uuid4()),
                filename=getattr(
                    resource,
                    "name",
                    "uploaded_file",
                ),
                content=content,
            )

        raise TypeError(
            f"Unsupported resource type: {type(resource)}"
        )