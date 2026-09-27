"""
knowledge/graph.py

Knowledge Graph domain model.

This graph is generated from a processed KnowledgeBase and serves as the
primary input to the Goal Generator.

It intentionally does NOT contain interview state, assessment state,
or evidence.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Enumerations
# ============================================================

class NodeType(str, Enum):
    TOPIC = "topic"
    CONCEPT = "concept"
    OUTCOME = "learning_outcome"
    EXAMPLE = "example"
    MISCONCEPTION = "misconception"


class EdgeType(str, Enum):
    CONTAINS = "contains"
    REQUIRES = "requires"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    EXTENDS = "extends"
    DEPENDS_ON = "depends_on"
    EXPLAINS = "explains"
    EXAMPLE_OF = "example_of"


# ============================================================
# Graph Node
# ============================================================

class GraphNode(BaseModel):
    """
    Generic node in the knowledge graph.
    """

    id: str

    type: NodeType

    label: str

    description: Optional[str] = None

    attributes: Dict[str, str] = Field(default_factory=dict)


# ============================================================
# Graph Edge
# ============================================================

class GraphEdge(BaseModel):
    """
    Directed relationship between two nodes.
    """

    source: str

    target: str

    relation: EdgeType

    weight: float = Field(default=1.0, ge=0.0)


# ============================================================
# Knowledge Graph
# ============================================================

class KnowledgeGraph(BaseModel):
    """
    Canonical graph representation of processed knowledge.

    This graph is generated AFTER knowledge processing and BEFORE
    goal generation.
    """

    knowledge_base_id: str

    nodes: List[GraphNode] = Field(default_factory=list)

    edges: List[GraphEdge] = Field(default_factory=list)

    root_topics: List[str] = Field(default_factory=list)

    adjacency: Dict[str, List[str]] = Field(default_factory=dict)

    reverse_adjacency: Dict[str, List[str]] = Field(default_factory=dict)

    metadata: Dict[str, str] = Field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """
        Retrieve a node by id.
        """
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def children(self, node_id: str) -> List[str]:
        """
        Return all outgoing neighbors.
        """
        return self.adjacency.get(node_id, [])

    def parents(self, node_id: str) -> List[str]:
        """
        Return all incoming neighbors.
        """
        return self.reverse_adjacency.get(node_id, [])

    def outgoing_edges(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming_edges(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.target == node_id]