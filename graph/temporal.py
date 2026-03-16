import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_graph_slice(db, as_of: str) -> dict:
    entities = db.fetch("""
        SELECT DISTINCT e.id, e.name, e.type, e.description,
               ev.role, ev.attributes, ev.valid_from, ev.valid_to, ev.change_type
        FROM kg_entities e
        JOIN kg_entity_versions ev ON ev.entity_id = e.id
        WHERE ev.valid_from <= %s AND (ev.valid_to IS NULL OR ev.valid_to >= %s)
        ORDER BY e.name
    """, [as_of, as_of])

    relationships = db.fetch("""
        SELECT r.type, r.description, r.weight,
               s.name AS source_name, t.name AS target_name
        FROM kg_relationships r
        JOIN kg_entities s ON r.source_id = s.id
        JOIN kg_entities t ON r.target_id = t.id
        WHERE (r.valid_from IS NULL OR r.valid_from <= %s)
          AND (r.valid_to IS NULL OR r.valid_to >= %s)
        ORDER BY r.weight DESC LIMIT 100
    """, [as_of, as_of])

    events = db.fetch("""
        SELECT event_type, event_date, description, entity_ids
        FROM kg_events
        WHERE event_date <= %s
        ORDER BY event_date DESC LIMIT 20
    """, [as_of])

    return _format_slice(f"Graph slice as of {as_of}", entities, relationships, events)


def compare_slices(db, date_a: str, date_b: str) -> dict:
    slice_a = _get_entity_set(db, date_a)
    slice_b = _get_entity_set(db, date_b)

    names_a = {e["name"] for e in slice_a}
    names_b = {e["name"] for e in slice_b}

    added   = names_b - names_a
    removed = names_a - names_b
    common  = names_a & names_b

    changed = []
    for name in common:
        ea = next(e for e in slice_a if e["name"] == name)
        eb = next(e for e in slice_b if e["name"] == name)
        if ea.get("role") != eb.get("role") or ea.get("attributes") != eb.get("attributes"):
            changed.append({"name": name, "before": ea, "after": eb})

    events_between = db.fetch("""
        SELECT event_type, event_date, description, entity_ids
        FROM kg_events
        WHERE event_date >= %s AND event_date <= %s
        ORDER BY event_date
    """, [date_a, date_b])

    parts = [f"## Comparison: {date_a} → {date_b}"]
    if added:
        parts.append(f"\n### New entities ({len(added)})")
        for n in sorted(added):
            parts.append(f"  - {n}")
    if removed:
        parts.append(f"\n### Removed entities ({len(removed)})")
        for n in sorted(removed):
            parts.append(f"  - {n}")
    if changed:
        parts.append(f"\n### Changed entities ({len(changed)})")
        for c in changed:
            parts.append(f"  - {c['name']}: role {c['before'].get('role','?')} → "
                         f"{c['after'].get('role','?')}")
    if events_between:
        parts.append(f"\n### Events in period ({len(events_between)})")
        for ev in events_between:
            parts.append(f"  - [{ev['event_date']}] {ev['event_type']}: {ev.get('description','')}")

    parts.append(f"\nSummary: +{len(added)} -{len(removed)} ~{len(changed)} entities, "
                 f"{len(events_between)} events")
    return {"comparison": "\n".join(parts)}


def get_entity_timeline(db, query: str) -> dict:
    entities = db.fetch("""
        SELECT id, name, type, description
        FROM kg_entities
        WHERE name ILIKE %s OR %s = ANY(aliases)
        LIMIT 5
    """, [f"%{query}%", query])

    if not entities:
        return {"timeline": f"No entities found matching '{query}'."}

    parts = ["## Entity Timeline"]
    for entity in entities:
        eid = entity["id"]
        parts.append(f"\n### {entity['name']} ({entity['type']})")
        parts.append(f"Description: {entity.get('description', 'N/A')}")

        versions = db.fetch("""
            SELECT valid_from, valid_to, role, attributes, change_type,
                   change_source, confidence, date_precision
            FROM kg_entity_versions
            WHERE entity_id = %s
            ORDER BY valid_from ASC NULLS FIRST
        """, [eid])

        if versions:
            parts.append("Timeline:")
            for v in versions:
                period = f"{v['valid_from'] or '?'} → {v['valid_to'] or 'present'}"
                attrs = v.get("attributes", {})
                attr_str = f", attrs={attrs}" if attrs else ""
                parts.append(f"  - [{period}] {v['change_type']}: role={v.get('role', '?')}"
                             f" (confidence={v.get('confidence', 1.0)}{attr_str})")

        events = db.fetch("""
            SELECT event_type, event_date, date_precision, description
            FROM kg_events
            WHERE %s = ANY(entity_ids)
            ORDER BY event_date ASC
        """, [eid])

        if events:
            parts.append("Events:")
            for ev in events:
                parts.append(f"  - [{ev['event_date']}] {ev['event_type']}: "
                             f"{ev.get('description', '')}")

        rels = db.fetch("""
            SELECT r.type, r.description, r.valid_from, r.valid_to,
                   CASE WHEN r.source_id = %s THEN t.name ELSE s.name END AS other_name,
                   CASE WHEN r.source_id = %s THEN 'outgoing' ELSE 'incoming' END AS direction
            FROM kg_relationships r
            JOIN kg_entities s ON r.source_id = s.id
            JOIN kg_entities t ON r.target_id = t.id
            WHERE r.source_id = %s OR r.target_id = %s
            ORDER BY r.valid_from ASC NULLS FIRST
        """, [eid, eid, eid, eid])

        if rels:
            parts.append("Relationships:")
            for r in rels:
                period = f"{r['valid_from'] or '?'} → {r['valid_to'] or 'present'}"
                arrow = "-->" if r["direction"] == "outgoing" else "<--"
                parts.append(f"  - {arrow} {r['other_name']} [{r['type']}] ({period}): "
                             f"{r.get('description', '')}")

    return {"timeline": "\n".join(parts)}


def _get_entity_set(db, as_of: str) -> list:
    return db.fetch("""
        SELECT DISTINCT e.name, e.type, ev.role, ev.attributes
        FROM kg_entities e
        JOIN kg_entity_versions ev ON ev.entity_id = e.id
        WHERE ev.valid_from <= %s AND (ev.valid_to IS NULL OR ev.valid_to >= %s)
    """, [as_of, as_of])


def _format_slice(title: str, entities: list, relationships: list, events: list) -> dict:
    parts = [f"## {title}"]
    parts.append(f"\n### Entities ({len(entities)})")
    for e in entities:
        role = f", role={e['role']}" if e.get("role") else ""
        parts.append(f"  - {e['name']} ({e['type']}){role}: {e.get('description', '')}")

    if relationships:
        parts.append(f"\n### Relationships ({len(relationships)})")
        for r in relationships:
            parts.append(f"  - {r['source_name']} --[{r['type']}]--> {r['target_name']}"
                         f" (w={r['weight']:.1f})")

    if events:
        parts.append(f"\n### Recent Events ({len(events)})")
        for ev in events:
            parts.append(f"  - [{ev['event_date']}] {ev['event_type']}: "
                         f"{ev.get('description', '')}")

    return {"slice": "\n".join(parts)}
