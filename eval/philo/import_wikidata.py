"""
Build philosophy graph from Wikidata (open) using SPARQL.
v1.1: philosophers + schools (P135) + influence (P737, P941) + criticized/opposed (P1628, P2453).
We DO NOT scrape Deniz database.
"""
import os
import re
import time
from typing import Dict, List, Optional

import requests
import yaml

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
UA = os.environ.get("PHILO_UA", "Phi-Bot/1.0 (https://github.com/UmbpW/Phi_Bot)")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def birth_year_from_iso(birth: Optional[str]) -> Optional[int]:
    """Extract year from ISO date like '1724-04-22T00:00:00Z'."""
    if not birth or not isinstance(birth, str):
        return None
    try:
        return int(birth[:4])
    except (ValueError, TypeError):
        return None


def era_from_year(y: Optional[int]) -> Optional[str]:
    """Map birth year to era."""
    if y is None:
        return None
    if y < 500:
        return "ancient"
    if y < 1500:
        return "medieval"
    if y < 1800:
        return "early_modern"
    if y < 1950:
        return "modern"
    return "contemporary"


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (name or "").strip().lower())
    s = re.sub(r"\s+", "_", s)
    return s[:80] or "unknown"


def sparql(query: str) -> dict:
    r = requests.get(
        SPARQL_ENDPOINT,
        params={"format": "json", "query": query},
        headers={"User-Agent": UA},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def pull_philosophers_with_movements(limit: int = 500) -> List[dict]:
    """Philosophers with birth/death and optional movement (P135)."""
    q = f"""
    SELECT ?person ?personLabel ?birth ?death ?movement ?movementLabel WHERE {{
      ?person wdt:P106 wd:Q4964182.
      OPTIONAL {{ ?person wdt:P569 ?birth. }}
      OPTIONAL {{ ?person wdt:P570 ?death. }}
      OPTIONAL {{ ?person wdt:P135 ?movement. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }}
    }} LIMIT {limit}
    """
    return sparql(q).get("results", {}).get("bindings", [])


def pull_influences(limit: int = 2000) -> List[dict]:
    q = f"""
    SELECT ?a ?aLabel ?b ?bLabel ?prop WHERE {{
      {{ ?a wdt:P737 ?b. BIND("P737" as ?prop) }}
      UNION
      {{ ?a wdt:P941 ?b. BIND("P941" as ?prop) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }}
    }} LIMIT {limit}
    """
    return sparql(q).get("results", {}).get("bindings", [])


def pull_opposes(limit: int = 500) -> List[dict]:
    """Best-effort: Wikidata has no standard 'opposes/criticizes' for philosophers.
    P1628=equivalent property, P2453=nominee — wrong IDs. Returns empty; use manual_edges.yaml."""
    return []


def _safe_year(raw) -> Optional[int]:
    if not raw:
        return None
    val = raw.get("value") if isinstance(raw, dict) else raw
    if not val or not isinstance(val, str):
        return None
    if val[0].isdigit():
        try:
            return int(val[:4])
        except ValueError:
            pass
    return None


def load_manual_edges() -> List[dict]:
    """Load manual_edges.yaml and return list of edge dicts (with src_name, dst_name)."""
    path = os.path.join(_SCRIPT_DIR, "manual_edges.yaml")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("edges", [])


def build_db(
    out_path: str,
    ph_limit: int = 500,
    edge_limit: int = 2000,
    opposes_limit: int = 500,
) -> None:
    ph_rows = pull_philosophers_with_movements(ph_limit)
    influences_raw = pull_influences(edge_limit)
    opposes_raw = pull_opposes(opposes_limit)
    manual = load_manual_edges()

    nodes_map: Dict[str, dict] = {}

    def ensure_philosopher(
        qid_url: str,
        label: str,
        birth: Optional[str] = None,
        death: Optional[str] = None,
    ) -> str:
        qid = qid_url.rsplit("/", 1)[-1]
        node_id = _slug(label) + "_" + qid.lower()
        if node_id in nodes_map:
            return node_id
        y = birth_year_from_iso(birth)
        era = era_from_year(y)
        nodes_map[node_id] = {
            "id": node_id,
            "name": label,
            "kind": "philosopher",
            "birth_year": y,
            "born": y,
            "died": _safe_year({"value": death} if isinstance(death, str) else death) if death else None,
            "era": era,
            "region": None,
            "tags": [],
            "description": None,
            "centrality": 0,
            "sources": {"wikidata": qid, "wikipedia": None, "sep": None, "external": []},
        }
        return node_id

    def ensure_school(qid_url: str, label: str) -> str:
        qid = qid_url.rsplit("/", 1)[-1]
        node_id = "school_" + _slug(label) + "_" + qid.lower()
        if node_id in nodes_map:
            return node_id
        nodes_map[node_id] = {
            "id": node_id,
            "name": label,
            "kind": "school",
            "birth_year": None,
            "born": None,
            "died": None,
            "era": None,
            "region": None,
            "tags": [],
            "description": None,
            "centrality": 0,
            "sources": {"wikidata": qid, "wikipedia": None, "sep": None, "external": []},
        }
        return node_id

    # Philosophers + member_of from movements
    for row in ph_rows:
        person = row.get("person", {}).get("value", "")
        label = row.get("personLabel", {}).get("value", "Unknown")
        birth = row.get("birth", {}).get("value")
        death = row.get("death", {}).get("value")
        ph_id = ensure_philosopher(person, label, birth, death)
        mov_url = row.get("movement", {}).get("value")
        mov_label = row.get("movementLabel", {}).get("value")
        if mov_url and mov_label:
            school_id = ensure_school(mov_url, mov_label)

    out_edges: List[dict] = []

    def add_edge(src: str, dst: str, rel: str, provenance: Optional[dict] = None, note: Optional[str] = None):
        wd_props = []
        if provenance and provenance.get("property"):
            p = provenance["property"]
            wd_props = [p] if isinstance(p, str) else p
        out_edges.append({
            "src": src,
            "dst": dst,
            "rel": rel,
            "weight": 0.7,
            "note": note,
            "sources": {"wikidata": wd_props, "external": []},
            "provenance": provenance,
        })

    # member_of edges (philosopher -> school)
    for row in ph_rows:
        person = row.get("person", {}).get("value", "")
        plabel = row.get("personLabel", {}).get("value", "Unknown")
        mov_url = row.get("movement", {}).get("value")
        mov_label = row.get("movementLabel", {}).get("value")
        if mov_url and mov_label:
            ph_id = ensure_philosopher(
                person, plabel,
                row.get("birth", {}).get("value"),
                row.get("death", {}).get("value"),
            )
            school_id = ensure_school(mov_url, mov_label)
            add_edge(ph_id, school_id, "member_of", {"source": "wikidata", "property": "P135"})

    # Influence edges
    for row in influences_raw:
        a_url = row.get("a", {}).get("value", "")
        b_url = row.get("b", {}).get("value", "")
        a_label = row.get("aLabel", {}).get("value", "Unknown")
        b_label = row.get("bLabel", {}).get("value", "Unknown")
        prop = row.get("prop", {}).get("value", "")
        a_id = ensure_philosopher(a_url, a_label)
        b_id = ensure_philosopher(b_url, b_label)
        if prop == "P737":
            rel = "influenced_by"
            src, dst = a_id, b_id
        else:
            rel = "influenced"
            src, dst = a_id, b_id
        add_edge(src, dst, rel, {"source": "wikidata", "property": prop})

    # Opposes / opposed_by (best-effort)
    for row in opposes_raw:
        p_url = row.get("person", {}).get("value", "")
        t_url = row.get("target", {}).get("value", "")
        p_label = row.get("personLabel", {}).get("value", "Unknown")
        t_label = row.get("targetLabel", {}).get("value", "Unknown")
        prop = row.get("prop", {}).get("value", "")
        p_id = ensure_philosopher(p_url, p_label)
        t_id = ensure_philosopher(t_url, t_label)
        if prop == "P1628":
            add_edge(p_id, t_id, "criticized", {"source": "wikidata", "property": "P1628"})
        else:
            add_edge(p_id, t_id, "opposed_by", {"source": "wikidata", "property": "P2453"})

    # Manual edges: resolve by name (exact or partial)
    def _resolve_name(name: str) -> Optional[str]:
        key = (name or "").strip().lower()
        for n in nodes_map.values():
            if n["kind"] == "philosopher" and n["name"].lower() == key:
                return n["id"]
        for n in nodes_map.values():
            if n["kind"] == "philosopher" and key in n["name"].lower():
                return n["id"]
        return None

    for me in manual:
        src_name = (me.get("src_name") or "").strip()
        dst_name = (me.get("dst_name") or "").strip()
        rel = me.get("rel") or "criticized"
        note = me.get("note")
        prov = me.get("provenance") or {"source": "manual"}
        src_id = _resolve_name(src_name)
        dst_id = _resolve_name(dst_name)
        if src_id and dst_id:
            add_edge(src_id, dst_id, rel, prov, note)
            out_edges[-1]["sources"] = {"wikidata": [], "external": []}
            out_edges[-1]["provenance"] = prov

    # Compute centrality (degree)
    deg: Dict[str, int] = {nid: 0 for nid in nodes_map}
    for e in out_edges:
        if e["src"] in deg:
            deg[e["src"]] += 1
        if e["dst"] in deg:
            deg[e["dst"]] += 1
    for n in nodes_map.values():
        n["centrality"] = deg.get(n["id"], 0)

    db = {
        "version": 1.1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nodes": list(nodes_map.values()),
        "edges": out_edges,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(db, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"Written {out_path} — nodes={len(nodes_map)}, edges={len(out_edges)}")


if __name__ == "__main__":
    out = os.environ.get("PHILO_DB_OUT", "eval/philo/philo_db.yaml")
    build_db(
        out_path=out,
        ph_limit=int(os.environ.get("PHILO_PH_LIMIT", "500")),
        edge_limit=int(os.environ.get("PHILO_EDGE_LIMIT", "2000")),
        opposes_limit=int(os.environ.get("PHILO_OPPOSES_LIMIT", "500")),
    )
