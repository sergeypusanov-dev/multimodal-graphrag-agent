import logging
from database import get_db

logger = logging.getLogger(__name__)


def build_graph_context(chunks: list, query_mode: str,
                        date_a: str = None, state: dict = None) -> str:
    if query_mode == "global":
        return _global_context()
    elif query_mode == "events":
        return _events_context(date_a)
    elif query_mode == "temporal":
        return _temporal_context(chunks, date_a)
    else:
        return _local_context(chunks)


def _local_context(chunks: list) -> str:
    db = get_db()
    entity_ids = set()
    for chunk in chunks:
        payload = chunk.payload if hasattr(chunk, "payload") else chunk
        for eid in payload.get("entity_ids", []):
            entity_ids.add(eid)

    if not entity_ids:
        return _chunks_to_text(chunks)

    placeholders = ",".join(["%s"] * len(entity_ids))
    entities = db.fetch(
        f"SELECT id, name, type, description FROM kg_entities WHERE id::text IN ({placeholders})",
        list(entity_ids))

    rels = db.fetch(f"""
        SELECT r.type, r.description, r.weight,
               s.name AS source_name, t.name AS target_name
        FROM kg_relationships r
        JOIN kg_entities s ON r.source_id = s.id
        JOIN kg_entities t ON r.target_id = t.id
        WHERE r.source_id::text IN ({placeholders}) OR r.target_id::text IN ({placeholders})
        ORDER BY r.weight DESC LIMIT 50
    """, list(entity_ids) + list(entity_ids))

    parts = ["## Entities"]
    for e in entities:
        parts.append(f"- {e['name']} ({e['type']}): {e.get('description', '')}")

    if rels:
        parts.append("\n## Relationships")
        for r in rels:
            parts.append(f"- {r['source_name']} --[{r['type']}]--> {r['target_name']}"
                         f": {r.get('description', '')} (w={r['weight']:.1f})")

    parts.append("\n## Relevant Chunks")
    parts.append(_chunks_to_text(chunks))
    return "\n".join(parts)


def _global_context() -> str:
    db = get_db()
    communities = db.fetch("""
        SELECT title, summary, rank FROM kg_communities
        ORDER BY rank DESC LIMIT 10
    """)
    if not communities:
        top_entities = db.fetch("""
            SELECT e.name, e.type, e.description, COUNT(r.id) AS rel_count
            FROM kg_entities e
            LEFT JOIN kg_relationships r ON r.source_id = e.id OR r.target_id = e.id
            GROUP BY e.id ORDER BY rel_count DESC LIMIT 20
        """)
        parts = ["## Top Entities (Global)"]
        for e in top_entities:
            parts.append(f"- {e['name']} ({e['type']}): {e.get('description', '')} "
                         f"[{e['rel_count']} relationships]")
        return "\n".join(parts)

    parts = ["## Community Summaries (Global)"]
    for c in communities:
        parts.append(f"### {c['title']} (rank={c['rank']:.2f})\n{c['summary']}")
    return "\n".join(parts)


def _temporal_context(chunks: list, date_a: str = None) -> str:
    db = get_db()
    params = []
    where = ""
    if date_a:
        where = "WHERE ev.valid_from <= %s OR ev.valid_from IS NULL"
        params = [date_a]

    versions = db.fetch(f"""
        SELECT ev.valid_from, ev.valid_to, ev.role, ev.attributes, ev.change_type,
               e.name, e.type
        FROM kg_entity_versions ev
        JOIN kg_entities e ON ev.entity_id = e.id
        {where}
        ORDER BY ev.valid_from DESC NULLS LAST LIMIT 30
    """, params)

    parts = ["## Temporal Context"]
    for v in versions:
        period = f"{v['valid_from'] or '?'} → {v['valid_to'] or 'present'}"
        parts.append(f"- {v['name']} ({v['type']}): {v['change_type']} [{period}] "
                     f"role={v.get('role', '?')}")

    parts.append("\n## Relevant Chunks")
    parts.append(_chunks_to_text(chunks))
    return "\n".join(parts)


def _events_context(date_a: str = None) -> str:
    db = get_db()
    params = []
    where = ""
    if date_a:
        where = "WHERE ev.event_date >= %s"
        params = [date_a]

    events = db.fetch(f"""
        SELECT ev.event_type, ev.event_date, ev.date_precision, ev.description, ev.entity_ids
        FROM kg_events ev
        {where}
        ORDER BY ev.event_date DESC LIMIT 30
    """, params)

    if not events:
        return "No events found for the specified period."

    db_entities = {}
    all_ids = set()
    for ev in events:
        for eid in (ev.get("entity_ids") or []):
            all_ids.add(str(eid))
    if all_ids:
        placeholders = ",".join(["%s"] * len(all_ids))
        rows = db.fetch(
            f"SELECT id, name FROM kg_entities WHERE id::text IN ({placeholders})",
            list(all_ids))
        db_entities = {str(r["id"]): r["name"] for r in rows}

    parts = ["## Events"]
    for ev in events:
        names = [db_entities.get(str(eid), str(eid)) for eid in (ev.get("entity_ids") or [])]
        parts.append(f"- [{ev['event_date']}] {ev['event_type']}: {ev.get('description', '')} "
                     f"(entities: {', '.join(names)})")
    return "\n".join(parts)


def _chunks_to_text(chunks: list) -> str:
    parts = []
    for c in chunks:
        payload = c.payload if hasattr(c, "payload") else c
        text = payload.get("text", "")
        source = payload.get("source_file", "unknown")
        parts.append(f"[source: {source}]\n{text}")
    return "\n---\n".join(parts)
