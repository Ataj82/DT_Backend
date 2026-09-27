from types import SimpleNamespace

import pytest

from app.interview.knowledge_retriever import KnowledgeRetriever


class FakeRepository:
    def __init__(self, text):
        self.text = text

    def retrieve(self, indicator):
        return self.text


def test_retriever_preserves_short_context():
    text = "Python functions return values."
    retriever = KnowledgeRetriever(
        knowledge_repository=FakeRepository(text),
    )

    assert retriever.retrieve(SimpleNamespace(name="functions")) == text


def test_retriever_bounds_long_context():
    text = "Paragraph one.\n" + ("Python programming knowledge. " * 300)
    retriever = KnowledgeRetriever(
        knowledge_repository=FakeRepository(text),
        max_context_chars=1000,
    )

    result = retriever.retrieve(SimpleNamespace(name="python"))

    assert len(result) <= 1000 + len(
        "\n[Knowledge context truncated for model context limits.]"
    )
    assert result.endswith(
        "[Knowledge context truncated for model context limits.]"
    )


def test_retriever_rejects_unreasonably_small_budget():
    with pytest.raises(ValueError):
        KnowledgeRetriever(
            knowledge_repository=FakeRepository("x"),
            max_context_chars=100,
        )
