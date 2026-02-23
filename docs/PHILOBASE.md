# PhiloBase v1 / v1.1

## What it is

Local open philosophy graph:
- **Nodes**: philosophers, schools (movements), concepts
- **Edges**: influenced_by / influenced / member_of / criticized / opposed_by
- **Sources**: Wikidata Q-ids and properties, plus optional external reference links

## Why Deniz site is still useful

Deniz Cem Önduygu's visualization is an excellent exploration UI and curated perspective, but appears "All rights reserved". We do NOT copy it. We can:
- Provide links-out to his browse page for visual exploration
- Use it for manual verification or for user "go deeper" navigation

## How to build

```bash
PHILO_UA="Phi-Bot/1.0 (https://github.com/...)" python3 eval/philo/import_wikidata.py
```

Optional env vars:
- `PHILO_DB_OUT` — output path (default: eval/philo/philo_db.yaml)
- `PHILO_PH_LIMIT` — max philosophers (default: 500)
- `PHILO_EDGE_LIMIT` — max influence edges (default: 2000)

## How bot uses it

When the user asks about influence links or "connections" (e.g. "кто на кого влиял", "связи философов", "карта философов"), the bot:
- Routes to philosophy pipeline with `[PHILO_DB]` hint in system prompt
- Answers in Markdown with citations/provenance
- Can suggest link-out to Deniz site as reference (without claiming data copied)

## Manual tests

- "покажи связи: Кант и Юм"
- "кто на кого влиял: Аристотель и Фома Аквинский"
- "дай граф влияний стоиков"

Expected:
- Markdown readable
- Mentions Wikidata as source
- No money/finance template leakage

## Query layer

```python
from eval.philo.query import PhiloDB

db = PhiloDB("eval/philo/philo_db.yaml")
db.find_by_name("Kant")
db.neighbors(node_id, rel="influenced_by")
db.get_schools(person_id)      # member_of edges
db.top_neighbors(node_id, rel=None, limit=10)  # by centrality
db.shortest_path(src_id, dst_id)
```

---

## v1.1 — Semantic Layer

### Schools (P135)

- Philosophers linked to movements via `member_of` edges
- School nodes created from Wikidata P135 (philosophical movement)

### Era (P569)

- `birth_year` from birth date
- `era`: ancient (<500) | medieval (<1500) | early_modern (<1800) | modern (<1950) | contemporary

### Criticized / Opposed (best-effort)

- Wikidata has no standard "opposes/criticizes" property for philosophers (P1628/P2453 are different).
- **manual_edges.yaml**: seed examples (Nietzsche→Schopenhauer, Popper→Plato); extend as needed.

### Centrality

- Degree (adjacent edges) computed at import; used for `top_neighbors()` ranking
