"""Query layer for PhiloBase: get_influences, neighbors, shortest_path, get_schools, top_neighbors."""
import os
from collections import defaultdict, deque
from typing import List, Optional

import yaml


def _compute_centrality(nodes: list, edges: list) -> dict:
    """Degree centrality: count of adjacent edges per node."""
    deg: dict = {}
    for n in nodes:
        deg[n["id"]] = 0
    for e in edges:
        if e["src"] in deg:
            deg[e["src"]] += 1
        if e["dst"] in deg:
            deg[e["dst"]] += 1
    return deg


class PhiloDB:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            self.data = {"nodes": [], "edges": []}
        else:
            with open(path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {"nodes": [], "edges": []}
        self.nodes = {n["id"]: n for n in self.data.get("nodes", [])}
        self.edges = self.data.get("edges", [])
        deg = _compute_centrality(list(self.nodes.values()), self.edges)
        for nid, d in deg.items():
            if nid in self.nodes:
                self.nodes[nid]["centrality"] = d
        self.name_index = defaultdict(list)
        for n in self.nodes.values():
            self.name_index[n["name"].lower()].append(n["id"])
        self.out = defaultdict(list)
        self.inc = defaultdict(list)
        for e in self.edges:
            self.out[e["src"]].append(e)
            self.inc[e["dst"]].append(e)

    def find_by_name(self, name: str) -> List[dict]:
        ids = self.name_index.get((name or "").strip().lower(), [])
        return [self.nodes[i] for i in ids]

    def neighbors(self, node_id: str, rel: Optional[str] = None) -> List[dict]:
        """Outgoing edges from node_id. rel filters by edge type."""
        edges = self.out.get(node_id, [])
        if rel:
            edges = [e for e in edges if e.get("rel") == rel]
        return edges

    def get_schools(self, person_id: str) -> List[dict]:
        """Edges person -> school (member_of)."""
        return self.neighbors(person_id, rel="member_of")

    def get_influences(self, node_id: str) -> List[dict]:
        """Edges where node was influenced (incoming) or influenced others (outgoing)."""
        inc = [dict(e, direction="in") for e in self.inc.get(node_id, [])]
        out = [dict(e, direction="out") for e in self.out.get(node_id, [])]
        return inc + out

    def top_neighbors(
        self,
        node_id: str,
        rel: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """Neighbors sorted by centrality (desc). Returns list of (edge, neighbor_node)."""
        edges = self.neighbors(node_id, rel)
        results = []
        for e in edges:
            nid = e["dst"]
            if nid in self.nodes:
                n = self.nodes[nid]
                results.append((e, n))
        results.sort(key=lambda x: x[1].get("centrality", 0), reverse=True)
        return results[:limit]

    def shortest_path(self, src: str, dst: str, max_depth: int = 6) -> Optional[List[str]]:
        """BFS along influence edges (outgoing + incoming = bidirectional)."""
        q = deque([(src, [src])])
        seen = {src}
        while q:
            cur, path = q.popleft()
            if cur == dst:
                return path
            if len(path) >= max_depth:
                continue
            for e in self.out.get(cur, []) + self.inc.get(cur, []):
                nxt = e["dst"] if e["src"] == cur else e["src"]
                if nxt in seen:
                    continue
                seen.add(nxt)
                q.append((nxt, path + [nxt]))
        return None
