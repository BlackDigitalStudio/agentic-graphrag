"""
ENN - SQLite Graph Storage
Entities = neurons. Edges = synapses. No Neo4j, no Docker dependency.
"""

import json
import sqlite3
import os
import logging
from typing import List, Optional, Dict, Any, Tuple

from .models import GraphNode, GraphEdge, SubgraphResult, validate_tags

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("ENN_DB_PATH", "/app/data/enn.db")


class Storage:
    """SQLite-based graph storage. Drop-in replacement for Neo4j."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
            logger.info(f"SQLite connected: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
            return False

    def close(self):
        if self._conn:
            self._conn.close()
            logger.info("SQLite closed")

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                signature TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                line_start INTEGER DEFAULT 0,
                line_end INTEGER DEFAULT 0,
                source_code TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT '',
                UNIQUE(source_id, target_id, type)
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
        """)
        # Full-text search on name + summary
        try:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    node_id, name, summary, content=nodes, content_rowid=rowid
                )
            """)
        except Exception:
            pass  # FTS already exists or not supported
        self._conn.commit()

    def _sync_fts(self, node_id: str, name: str, summary: str):
        """Keep FTS index in sync."""
        try:
            self._conn.execute("INSERT OR REPLACE INTO nodes_fts(node_id, name, summary) VALUES (?, ?, ?)",
                               (node_id, name, summary))
        except Exception:
            pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    # ============== Node Operations ==============

    def create_node(self, node: GraphNode) -> bool:
        node.tags = validate_tags(node.tags)
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO nodes (node_id, type, name, signature, file_path,
                    line_start, line_end, source_code, summary, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node.node_id, node.type, node.name, node.signature, node.file_path,
                  node.line_start, node.line_end, node.source_code, node.summary,
                  json.dumps(node.tags), node.created_at, node.updated_at))
            self._sync_fts(node.node_id, node.name, node.summary)
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Create node failed: {e}")
            return False

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        row = self._conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row:
            return self._row_to_node(row)
        return None

    def get_node_code(self, node_id: str) -> Optional[str]:
        node = self.get_node(node_id)
        return node.source_code if node else None

    def delete_node(self, node_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
        self._conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        self._conn.commit()
        return cur.rowcount > 0

    def get_nodes_bulk(self, node_ids: List[str]) -> List[GraphNode]:
        if not node_ids:
            return []
        placeholders = ",".join("?" * len(node_ids))
        rows = self._conn.execute(f"SELECT * FROM nodes WHERE node_id IN ({placeholders})", node_ids).fetchall()
        return [self._row_to_node(r) for r in rows]

    def update_node(self, node: GraphNode) -> bool:
        cur = self._conn.execute("UPDATE nodes SET summary = ?, updated_at = ? WHERE node_id = ?",
                                  (node.summary, node.updated_at, node.node_id))
        self._sync_fts(node.node_id, node.name, node.summary)
        self._conn.commit()
        return cur.rowcount > 0

    def bulk_create_nodes(self, nodes: List[GraphNode], chunk_size: int = 500) -> int:
        count = 0
        for i in range(0, len(nodes), chunk_size):
            chunk = nodes[i:i + chunk_size]
            for node in chunk:
                node.tags = validate_tags(node.tags)
                self._conn.execute("""
                    INSERT OR REPLACE INTO nodes (node_id, type, name, signature, file_path,
                        line_start, line_end, source_code, summary, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (node.node_id, node.type, node.name, node.signature, node.file_path,
                      node.line_start, node.line_end, node.source_code, node.summary,
                      json.dumps(node.tags), node.created_at, node.updated_at))
                self._sync_fts(node.node_id, node.name, node.summary)
                count += 1
            self._conn.commit()
        return count

    # ============== Edge Operations ==============

    def create_edge(self, edge: GraphEdge) -> bool:
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO edges (source_id, target_id, type, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (edge.source_id, edge.target_id, edge.edge_type,
                  json.dumps(edge.metadata), edge.created_at))
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Create edge failed: {e}")
            return False

    def delete_edge(self, source_id: str, target_id: str, edge_type: str) -> bool:
        cur = self._conn.execute("DELETE FROM edges WHERE source_id = ? AND target_id = ? AND type = ?",
                                  (source_id, target_id, edge_type))
        self._conn.commit()
        return cur.rowcount > 0

    def bulk_create_edges(self, edges: List[GraphEdge], chunk_size: int = 500) -> int:
        count = 0
        for i in range(0, len(edges), chunk_size):
            chunk = edges[i:i + chunk_size]
            for edge in chunk:
                self._conn.execute("""
                    INSERT OR REPLACE INTO edges (source_id, target_id, type, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (edge.source_id, edge.target_id, edge.edge_type,
                      json.dumps(edge.metadata), edge.created_at))
                count += 1
            self._conn.commit()
        return count

    # ============== Navigation ==============

    def get_neighbors(self, node_id: str, depth: int = 1, edge_types: List[str] = None,
                      direction: str = "both") -> Tuple[List[GraphNode], List[GraphEdge]]:
        nodes = {}
        edges = []
        visited = {node_id}
        frontier = [node_id]

        for _ in range(min(depth, 3)):
            next_frontier = []
            for nid in frontier:
                # Outgoing
                if direction in ("both", "outgoing"):
                    rows = self._conn.execute(
                        "SELECT * FROM edges WHERE source_id = ?", (nid,)).fetchall()
                    for r in rows:
                        if edge_types and r["type"] not in edge_types:
                            continue
                        edges.append(self._row_to_edge(r))
                        if r["target_id"] not in visited:
                            visited.add(r["target_id"])
                            next_frontier.append(r["target_id"])

                # Incoming
                if direction in ("both", "incoming"):
                    rows = self._conn.execute(
                        "SELECT * FROM edges WHERE target_id = ?", (nid,)).fetchall()
                    for r in rows:
                        if edge_types and r["type"] not in edge_types:
                            continue
                        edges.append(self._row_to_edge(r))
                        if r["source_id"] not in visited:
                            visited.add(r["source_id"])
                            next_frontier.append(r["source_id"])

            frontier = next_frontier

        # Fetch all neighbor nodes
        all_ids = list(visited)
        if all_ids:
            placeholders = ",".join("?" * len(all_ids))
            rows = self._conn.execute(f"SELECT * FROM nodes WHERE node_id IN ({placeholders})", all_ids).fetchall()
            nodes = {r["node_id"]: self._row_to_node(r) for r in rows}

        return list(nodes.values()), edges

    def get_subgraph(self, node_id: str, depth: int = 2, edge_types: List[str] = None,
                     include_code: bool = False) -> Optional[SubgraphResult]:
        center = self.get_node(node_id)
        if not center:
            return None
        nodes, edges = self.get_neighbors(node_id, depth, edge_types)
        if center.node_id not in {n.node_id for n in nodes}:
            nodes.insert(0, center)
        return SubgraphResult(
            center_node=center, nodes=nodes, edges=edges,
            depth=depth, total_nodes=len(nodes), total_edges=len(edges)
        )

    # ============== Search ==============

    def count_nodes(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM nodes").fetchone()
        return row["cnt"]

    def search_nodes(self, query: str = None, node_type: str = None,
                     tags: List[str] = None, limit: int = 50, skip: int = 0) -> List[GraphNode]:
        conditions = []
        params = []

        if query:
            conditions.append("(LOWER(name) LIKE ? OR LOWER(summary) LIKE ?)")
            params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
        if node_type:
            conditions.append("type = ?")
            params.append(node_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, skip])

        rows = self._conn.execute(
            f"SELECT * FROM nodes WHERE {where} ORDER BY node_id LIMIT ? OFFSET ?", params
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ============== Graph Navigation (for LLM agent) ==============

    def get_root_categories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Top entities by edge count (most connected neurons)."""
        rows = self._conn.execute("""
            SELECT n.node_id, n.type, n.name, n.summary, COUNT(e.id) as edge_count
            FROM nodes n
            LEFT JOIN edges e ON e.source_id = n.node_id
            WHERE n.type NOT IN ('document', 'cached_answer')
            GROUP BY n.node_id
            ORDER BY edge_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [{"node_id": r["node_id"], "type": r["type"], "name": r["name"], "summary": r["summary"]} for r in rows]

    def get_children(self, node_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get nodes connected via outgoing edges."""
        rows = self._conn.execute("""
            SELECT n.node_id, n.type, n.name, n.summary
            FROM edges e JOIN nodes n ON e.target_id = n.node_id
            WHERE e.source_id = ? LIMIT ?
        """, (node_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_related(self, node_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get all directly connected nodes with edge info."""
        results = []
        # Outgoing
        rows = self._conn.execute("""
            SELECT n.node_id, n.type, n.name, n.summary, e.type as edge_type, 1 as outgoing
            FROM edges e JOIN nodes n ON e.target_id = n.node_id
            WHERE e.source_id = ? LIMIT ?
        """, (node_id, limit)).fetchall()
        results.extend([dict(r) for r in rows])

        # Incoming
        rows = self._conn.execute("""
            SELECT n.node_id, n.type, n.name, n.summary, e.type as edge_type, 0 as outgoing
            FROM edges e JOIN nodes n ON e.source_id = n.node_id
            WHERE e.target_id = ? LIMIT ?
        """, (node_id, limit)).fetchall()
        results.extend([dict(r) for r in rows])

        return results[:limit]

    def get_chunks_for_entity(self, entity_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get document chunks that MENTION a given entity."""
        rows = self._conn.execute("""
            SELECT n.node_id, n.source_code as content, n.file_path, n.name
            FROM edges e
            JOIN nodes n ON e.source_id = n.node_id
            JOIN nodes target ON e.target_id = target.node_id
            WHERE target.name = ? AND e.type = 'MENTIONS' AND n.type = 'document'
            LIMIT ?
        """, (entity_name, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_evidence_for_entity(self, entity_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get evidence fragments from edges connected to an entity."""
        rows = self._conn.execute("""
            SELECT n1.name as source, n2.name as target, e.type as edge_type, e.metadata
            FROM edges e
            JOIN nodes n1 ON e.source_id = n1.node_id
            JOIN nodes n2 ON e.target_id = n2.node_id
            WHERE (n1.name = ? OR n2.name = ?) AND e.metadata != '{}'
            LIMIT ?
        """, (entity_name, entity_name, limit)).fetchall()

        evidences = []
        for r in rows:
            try:
                meta = json.loads(r["metadata"]) if r["metadata"] else {}
            except Exception:
                meta = {}
            ev_starts = meta.get("evidence_starts", "")
            ev_ends = meta.get("evidence_ends", "")
            if ev_starts or ev_ends:
                evidences.append({
                    "source": r["source"], "target": r["target"],
                    "edge_type": r["edge_type"],
                    "evidence_starts": ev_starts, "evidence_ends": ev_ends,
                    "source_chunk": meta.get("source_chunk", ""),
                })
        return evidences

    def search_entities_by_name(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search entities by name or summary — bidirectional for Russian declension."""
        if len(query) >= 3:
            # Try FTS first
            try:
                rows = self._conn.execute("""
                    SELECT n.node_id, n.type, n.name, n.summary
                    FROM nodes_fts fts JOIN nodes n ON fts.node_id = n.node_id
                    WHERE nodes_fts MATCH ? AND n.type != 'document'
                    LIMIT ?
                """, (query, limit)).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass

            # Fallback: LIKE search (bidirectional)
            q = query.lower()
            rows = self._conn.execute("""
                SELECT node_id, type, name, summary FROM nodes
                WHERE type != 'document'
                  AND (LOWER(name) LIKE ? OR LOWER(summary) LIKE ? OR ? LIKE '%' || LOWER(name) || '%')
                ORDER BY name LIMIT ?
            """, (f"%{q}%", f"%{q}%", q, limit)).fetchall()
        else:
            rows = self._conn.execute("""
                SELECT node_id, type, name, summary FROM nodes
                WHERE type != 'document' AND LOWER(name) = LOWER(?)
                LIMIT ?
            """, (query, limit)).fetchall()

        return [dict(r) for r in rows]

    # ============== Statistics ==============

    def get_stats(self) -> Dict[str, Any]:
        node_count = self._conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"]
        edge_count = self._conn.execute("SELECT COUNT(*) as c FROM edges").fetchone()["c"]
        types = self._conn.execute("SELECT DISTINCT type FROM nodes").fetchall()
        type_list = [r["type"] for r in types]
        return {
            "total_nodes": node_count,
            "total_edges": edge_count,
            "node_types": type_list,
            "type_count": len(type_list),
        }

    def clear_all(self):
        self._conn.execute("DELETE FROM edges")
        self._conn.execute("DELETE FROM nodes")
        try:
            self._conn.execute("DELETE FROM nodes_fts")
        except Exception:
            pass
        self._conn.commit()
        logger.info("Graph cleared")

    # ============== Helpers ==============

    def _row_to_node(self, row) -> GraphNode:
        tags = []
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except Exception:
            pass
        return GraphNode(
            node_id=row["node_id"], type=row["type"], name=row["name"],
            signature=row["signature"] or "", file_path=row["file_path"] or "",
            line_start=row["line_start"] or 0, line_end=row["line_end"] or 0,
            source_code=row["source_code"] or "", summary=row["summary"] or "",
            tags=tags, created_at=row["created_at"] or "", updated_at=row["updated_at"] or "",
        )

    def _row_to_edge(self, row) -> GraphEdge:
        meta = {}
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception:
            pass
        return GraphEdge(
            source_id=row["source_id"], target_id=row["target_id"],
            edge_type=row["type"], metadata=meta,
            created_at=row["created_at"] or "",
        )


# Backward compatibility alias
Neo4jStorage = Storage
