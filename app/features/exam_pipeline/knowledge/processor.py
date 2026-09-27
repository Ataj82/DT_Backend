"""
app/knowledge/processor.py

Transforms uploaded Documents into a populated KnowledgeBase and
constructs a KnowledgeGraph.

This implementation intentionally performs lightweight processing.
It can later be replaced by an LLM-based or NLP-based extractor without
changing the rest of the application.
"""

from __future__ import annotations

import re
from collections import Counter
from uuid import uuid4

from .graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
)
from .models import (
    BloomLevel,
    Concept,
    KnowledgeBase,
    LearningOutcome,
    Relationship,
    RelationshipType,
    Topic,
)


class KnowledgeProcessor:
    """
    Builds a structured KnowledgeBase from uploaded documents.
    """

    STOP_WORDS = {
        "the", "and", "for", "with", "that", "this",
        "from", "into", "there", "their", "about",
        "have", "will", "your", "been", "were",
        "which", "when", "what", "where", "while",
        "into", "than", "then", "also", "using",
        "used", "such", "each", "other", "more",
        "most", "many", "much", "very", "can",
        "could", "should", "would", "must",
        "you", "our", "its", "are", "was",
        "is", "of", "to", "in", "on", "as",
        "or", "by", "an", "be", "it", "at",
        "we", "a", "if", "not", "they", "he",
        "she", "them", "his", "her",
    }

    # ---------------------------------------------------------

    def process(
        self,
        knowledge_base: KnowledgeBase,
    ) -> KnowledgeGraph:
        """
        Populate the KnowledgeBase and construct its graph.
        """

        self._extract_topics(knowledge_base)
        self._extract_concepts(knowledge_base)
        self._extract_relationships(knowledge_base)
        self._extract_learning_outcomes(knowledge_base)

        graph = self._build_graph(knowledge_base)

        knowledge_base.graph = graph

        return graph

    # =========================================================
    # Topic Extraction
    # =========================================================

    def _extract_topics(
        self,
        kb: KnowledgeBase,
    ) -> None:

        kb.topics.clear()

        if not kb.documents:
            return

        for doc in kb.documents:

            kb.topics.append(
                Topic(
                    id=str(uuid4()),
                    title=doc.filename,
                    summary=doc.content[:200],
                    importance=1.0,
                )
            )

    # =========================================================
    # Concept Extraction
    # =========================================================

    def _extract_concepts(
        self,
        kb: KnowledgeBase,
    ) -> None:

        kb.concepts.clear()

        words = []

        for doc in kb.documents:

            tokens = re.findall(
                r"[A-Za-z][A-Za-z0-9_-]{2,}",
                doc.content,
            )

            words.extend(
                token.lower()
                for token in tokens
                if token.lower() not in self.STOP_WORDS
            )

        counter = Counter(words)

        #
        # Top 50 most frequent terms
        #

        for word, count in counter.most_common(50):

            kb.concepts.append(

                Concept(

                    id=str(uuid4()),

                    name=word,

                    definition=None,

                    difficulty=min(
                        1.0,
                        count / 20,
                    ),

                )

            )

    # =========================================================
    # Relationships
    # =========================================================

    def _extract_relationships(
        self,
        kb: KnowledgeBase,
    ) -> None:

        kb.relationships.clear()

        concepts = kb.concepts

        for i in range(len(concepts) - 1):

            kb.relationships.append(

                Relationship(

                    source_id=concepts[i].id,

                    target_id=concepts[i + 1].id,

                    relationship=RelationshipType.RELATED_TO,

                    weight=1.0,

                )

            )

    # =========================================================
    # Learning Outcomes
    # =========================================================

    def _extract_learning_outcomes(
        self,
        kb: KnowledgeBase,
    ) -> None:

        kb.learning_outcomes.clear()

        for concept in kb.concepts:

            kb.learning_outcomes.append(

                LearningOutcome(

                    id=str(uuid4()),

                    description=f"Understand {concept.name}",

                    bloom_level=BloomLevel.UNDERSTAND,

                    concept_ids=[concept.id],

                )

            )

    # =========================================================
    # Graph Construction
    # =========================================================

    def _build_graph(
        self,
        kb: KnowledgeBase,
    ) -> KnowledgeGraph:

        graph = KnowledgeGraph(

            knowledge_base_id=kb.id,

        )

        #
        # Topic nodes
        #

        for topic in kb.topics:

            graph.nodes.append(

                GraphNode(

                    id=topic.id,

                    type=NodeType.TOPIC,

                    label=topic.title,

                    description=topic.summary,

                )

            )

            graph.root_topics.append(topic.id)

        #
        # Concept nodes
        #

        for concept in kb.concepts:

            graph.nodes.append(

                GraphNode(

                    id=concept.id,

                    type=NodeType.CONCEPT,

                    label=concept.name,

                    description=concept.definition,

                )

            )

        #
        # Learning outcome nodes
        #

        for outcome in kb.learning_outcomes:

            graph.nodes.append(

                GraphNode(

                    id=outcome.id,

                    type=NodeType.OUTCOME,

                    label=outcome.description,

                )

            )

        #
        # Topic → Concept edges
        #

        if kb.topics:

            root = kb.topics[0].id

            for concept in kb.concepts:

                edge = GraphEdge(

                    source=root,

                    target=concept.id,

                    relation=EdgeType.CONTAINS,

                )

                graph.edges.append(edge)

        #
        # Concept relationships
        #

        for relation in kb.relationships:

            edge = GraphEdge(

                source=relation.source_id,

                target=relation.target_id,

                relation=EdgeType.RELATED_TO,

                weight=relation.weight,

            )

            graph.edges.append(edge)

        #
        # Outcome edges
        #

        for outcome in kb.learning_outcomes:

            for cid in outcome.concept_ids:

                graph.edges.append(

                    GraphEdge(

                        source=cid,

                        target=outcome.id,

                        relation=EdgeType.EXPLAINS,

                    )

                )

        #
        # Build adjacency tables
        #

        for edge in graph.edges:

            graph.adjacency.setdefault(
                edge.source,
                [],
            ).append(edge.target)

            graph.reverse_adjacency.setdefault(
                edge.target,
                [],
            ).append(edge.source)

        return graph