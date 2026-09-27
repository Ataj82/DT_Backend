"""
app/knowledge/document.py

Domain model representing one knowledge document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class Document:
    """
    One knowledge document.

    A document may originate from:
      - uploaded text
      - txt/pdf/docx loader
      - database
      - external knowledge source
    """

    filename: str

    content: str

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    language: str = "en"

    def __len__(self) -> int:
        return len(self.content)

    @property
    def text(self) -> str:
        """
        Compatibility alias.
        Some components use `document.text`,
        others use `document.content`.
        """
        return self.content