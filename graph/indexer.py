import json, logging, uuid
import yaml
from psycopg2.extensions import adapt, register_adapter, AsIs

from llm.adapter import batch_llm
from vector_store.adapter import store_chunk
from security.middleware import batch_circuit


def _uuid_array(uuids):
    """Cast list of UUID strings to PostgreSQL uuid[] literal."""
    if not uuids:
        return AsIs("'{}'::uuid[]")
    inner = ",".join(str(u) for u in uuids)
    return AsIs(f"ARRAY[{','.join(repr(str(u)) for u in uuids)}]::uuid[]")

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = """Extract entities and relationships from the following text.
Return JSON:
{
  "entities": [
    {"name": "...", "type": "person|org|place|event|concept|product|date", "description": "...", "aliases": []}
  ],
  "relationships": [
    {"source": "entity_name", "target": "entity_name", "type": "...", "description": "...", "weight": 1.0}
  ],
  "events": [
    {"entities": ["entity_name"], "event_type": "...", "date": "ISO or null", "date_precision": "day|month|year", "description": "..."}
  ]
}

Text:
"""


def run_indexing_pipeline(file_path: str, processed: dict, config: dict, db) -> dict:
    content    = processed.get("content", "")
    media_type = processed.get("media_type", "text")
    doc_id     = str(uuid.uuid4())
    doc_date   = processed.get("doc_date")

    chunks = _chunk_text(content, config)
    logger.info(f"Indexing {file_path}: {len(chunks)} chunks, media={media_type}")

    total_entities = 0
    for i, chunk_text in enumerate(chunks):
        extraction = _extract_entities(chunk_text)
        entity_ids = _upsert_entities(db, extraction.get("entities", []),
                                      media_type, file_path, doc_id)
        _upsert_relationships(db, extraction.get("relationships", []),
                              entity_ids, doc_date, doc_id)
        _upsert_events(db, extraction.get("events", []), entity_ids, doc_id, media_type)

        chunk_id = str(uuid.uuid4())
        metadata = {
            "doc_id": doc_id, "source_file": file_path, "media_type": media_type,
            "chunk_index": i,
        }
        if media_type == "audio" and processed.get("segments"):
            seg = processed["segments"][i] if i < len(processed["segments"]) else {}
            metadata["timestamp_ms"] = int(seg.get("start", 0) * 1000) if seg else None
        if media_type == "video":
            frames = processed.get("frames", [])
            metadata["frame_number"] = frames[i]["frame_number"] if i < len(frames) else None

        db.execute("""
            INSERT INTO kg_chunks (id, content, media_type, entity_ids, doc_id,
                                   source_file, chunk_index, timestamp_ms, frame_number, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [chunk_id, chunk_text, media_type,
              _uuid_array(list(entity_ids.values())) if entity_ids else AsIs("'{}'::uuid[]"),
              doc_id, file_path, i,
              metadata.get("timestamp_ms"), metadata.get("frame_number"),
              json.dumps(metadata)])

        emb_id = store_chunk(chunk_text, {
            "doc_id": doc_id, "source_file": file_path, "media_type": media_type,
            "chunk_index": i, "entity_ids": [str(e) for e in entity_ids.values()],
            "chunk_type": "content",
        }, chunk_id)

        db.execute("UPDATE kg_chunks SET embedding_id=%s WHERE id=%s", [emb_id, chunk_id])
        total_entities += len(entity_ids)

    return {"entities": total_entities, "chunks": len(chunks), "doc_id": doc_id}


def _chunk_text(text: str, config: dict) -> list:
    chunk_size = config["knowledge_base"]["chunk_size"]
    overlap    = config["knowledge_base"]["chunk_overlap"]
    if not text.strip():
        return []
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            words = current.split()
            overlap_words = int(overlap / max(1, len(current)) * len(words))
            current = " ".join(words[-overlap_words:]) + "\n\n" + para if overlap_words else para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    if not chunks and text.strip():
        chunks = [text.strip()]
    return chunks


def _extract_entities(text: str) -> dict:
    try:
        response = batch_circuit.call(
            batch_llm.chat,
            messages=[{"role": "user", "content": ENTITY_EXTRACTION_PROMPT + text[:3000]}]
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Entity extraction failed: {e}")
        return {"entities": [], "relationships": [], "events": []}


def _upsert_entities(db, entities: list, media_type: str,
                     source_file: str, doc_id: str) -> dict:
    name_to_id = {}
    for ent in entities:
        name = ent.get("name", "").strip()
        etype = ent.get("type", "concept").strip()
        if not name:
            continue
        existing = db.fetchone(
            "SELECT id FROM kg_entities WHERE name=%s AND type=%s", [name, etype])
        if existing:
            eid = existing["id"]
            db.execute("""
                UPDATE kg_entities SET description=COALESCE(NULLIF(%s,''), description),
                  media_type=%s, doc_ids=array_append(doc_ids, %s), updated_at=NOW()
                WHERE id=%s
            """, [ent.get("description", ""), media_type, doc_id, eid])
        else:
            eid = str(uuid.uuid4())
            db.execute("""
                INSERT INTO kg_entities (id, name, type, description, aliases,
                  media_type, source_file, doc_ids, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}')
            """, [eid, name, etype, ent.get("description", ""),
                  ent.get("aliases", []), media_type, source_file, [doc_id]])

            emb_text = f"{name} ({etype}): {ent.get('description', '')}"
            emb_id = store_chunk(emb_text, {
                "entity_id": eid, "chunk_type": "entity",
                "media_type": media_type, "doc_id": doc_id,
            })
            db.execute("UPDATE kg_entities SET embedding_id=%s WHERE id=%s", [emb_id, eid])

        name_to_id[name] = eid
    return name_to_id


def _upsert_relationships(db, relationships: list, name_to_id: dict,
                          doc_date: str, doc_id: str):
    for rel in relationships:
        src = name_to_id.get(rel.get("source"))
        tgt = name_to_id.get(rel.get("target"))
        if not src or not tgt:
            continue
        db.execute("""
            INSERT INTO kg_relationships (source_id, target_id, type, description,
              weight, valid_from, doc_ids)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, [src, tgt, rel.get("type", "related"), rel.get("description", ""),
              rel.get("weight", 1.0), doc_date, [doc_id]])


def _normalize_date(raw: str) -> str:
    """Normalize partial dates to valid ISO timestamps."""
    if not raw:
        return None
    raw = raw.strip()
    import re
    if re.match(r'^\d{4}$', raw):
        return f"{raw}-01-01"
    if re.match(r'^\d{4}-\d{1,2}$', raw):
        return f"{raw}-01"
    if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', raw):
        return raw
    return raw


def _upsert_events(db, events: list, name_to_id: dict,
                   doc_id: str, media_type: str):
    for evt in events:
        entity_names = evt.get("entities", [])
        entity_ids = [name_to_id[n] for n in entity_names if n in name_to_id]
        if not entity_ids:
            continue
        event_date = _normalize_date(evt.get("date"))
        if not event_date:
            continue
        db.execute("""
            INSERT INTO kg_events (entity_ids, event_type, event_date,
              date_precision, description, doc_ids, media_refs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, [_uuid_array(entity_ids), evt.get("event_type", "unknown"), event_date,
              evt.get("date_precision", "day"), evt.get("description", ""),
              [doc_id], json.dumps([{"type": media_type}])])
