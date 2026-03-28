"""
Tree Base - Graph Models
Data models for the universal knowledge graph.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json


@dataclass
class GraphNode:
    """
    Node in the knowledge graph.
    Can be a document chunk, entity, category, or any extracted concept.
    """
    node_id: str
    type: str
    name: str
    signature: str
    file_path: str
    line_start: int
    line_end: int
    source_code: str = ""
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "name": self.name,
            "signature": self.signature,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "source_code": self.source_code,
            "summary": self.summary,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_api_dict(self, include_code: bool = False) -> Dict[str, Any]:
        d = self.to_dict()
        if not include_code:
            d.pop("source_code", None)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        def _to_str(val) -> str:
            if val is None:
                return datetime.utcnow().isoformat()
            if isinstance(val, str):
                return val
            if hasattr(val, "isoformat"):
                return val.isoformat()
            return str(val)

        return cls(
            node_id=data["node_id"],
            type=data["type"],
            name=data["name"],
            signature=data.get("signature", ""),
            file_path=data.get("file_path", ""),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            source_code=data.get("source_code", ""),
            summary=data.get("summary", ""),
            tags=data.get("tags", []),
            created_at=_to_str(data.get("created_at")),
            updated_at=_to_str(data.get("updated_at")),
        )


@dataclass
class GraphEdge:
    """Edge in the knowledge graph."""
    source_id: str
    target_id: str
    edge_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.edge_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=data["type"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


@dataclass
class SubgraphResult:
    """Subgraph query result."""
    center_node: GraphNode
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    depth: int
    total_nodes: int
    total_edges: int

    def to_dict(self, include_code: bool = False) -> Dict[str, Any]:
        return {
            "center_node": self.center_node.to_api_dict(include_code),
            "nodes": [n.to_api_dict(include_code) for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "depth": self.depth,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
        }


@dataclass
class IngestResult:
    """Pipeline result."""
    success: bool
    files_processed: int
    nodes_created: int
    edges_created: int
    errors: List[str] = field(default_factory=list)


def validate_tags(tags: List[str]) -> List[str]:
    """Accept any tags — system does not restrict categories."""
    return [t.lower().strip() for t in tags if t and t.strip()]
