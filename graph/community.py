import logging, uuid
import networkx as nx
import yaml

from database import get_db
from llm.adapter import batch_llm
from vector_store.adapter import store_chunk
from security.middleware import batch_circuit

logger = logging.getLogger(__name__)
config = yaml.safe_load(open("config.yaml"))


def detect_communities():
    method = config["knowledge_base"].get("community_detection", "leiden")
    db = get_db()

    entities = db.fetch("SELECT id, name, type, description FROM kg_entities")
    relationships = db.fetch("""
        SELECT source_id, target_id, type, weight
        FROM kg_relationships
    """)

    if not entities or not relationships:
        logger.info("No entities/relationships for community detection.")
        return []

    G = nx.Graph()
    for e in entities:
        G.add_node(str(e["id"]), name=e["name"], type=e["type"],
                   description=e.get("description", ""))
    for r in relationships:
        G.add_edge(str(r["source_id"]), str(r["target_id"]),
                   rel_type=r["type"], weight=r.get("weight", 1.0))

    if method == "leiden":
        partitions = _leiden_partition(G)
    else:
        partitions = _louvain_partition(G)

    db.execute("DELETE FROM kg_communities")

    communities = []
    for level, partition in enumerate(partitions):
        for comm_id, node_ids in partition.items():
            if len(node_ids) < 2:
                continue
            entity_names = [G.nodes[n]["name"] for n in node_ids if n in G.nodes]
            entity_types = [G.nodes[n]["type"] for n in node_ids if n in G.nodes]
            inner_edges = [(u, v, G.edges[u, v]) for u, v in G.edges()
                          if u in node_ids and v in node_ids]

            summary_input = _build_community_prompt(entity_names, entity_types, inner_edges, G)
            summary = _summarize_community(summary_input)

            title = f"Community L{level}-{comm_id}: {', '.join(entity_names[:3])}"
            if len(entity_names) > 3:
                title += f" (+{len(entity_names) - 3})"

            rank = len(node_ids) * (1 + len(inner_edges) * 0.1)

            cid = str(uuid.uuid4())
            entity_uuids = [n for n in node_ids if n in {str(e["id"]) for e in entities}]

            db.execute("""
                INSERT INTO kg_communities (id, level, title, summary, entity_ids, rank)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, [cid, level, title, summary, entity_uuids, rank])

            emb_id = store_chunk(f"{title}\n{summary}", {
                "chunk_type": "community",
                "community_id": cid,
                "level": level,
            })
            db.execute("UPDATE kg_communities SET embedding_id=%s WHERE id=%s", [emb_id, cid])

            communities.append({
                "id": cid, "level": level, "title": title,
                "entity_count": len(node_ids), "rank": rank,
            })

    logger.info(f"Detected {len(communities)} communities using {method}")
    return communities


def _leiden_partition(G: nx.Graph) -> list:
    try:
        from graspologic.partition import hierarchical_leiden
        result = hierarchical_leiden(G, max_cluster_size=50, random_seed=42)
        levels = {}
        for node_id, community_id, level in result:
            levels.setdefault(level, {}).setdefault(community_id, set()).add(str(node_id))
        return [levels[l] for l in sorted(levels.keys())]
    except ImportError:
        logger.warning("graspologic not available, falling back to Louvain")
        return _louvain_partition(G)


def _louvain_partition(G: nx.Graph) -> list:
    communities = nx.community.louvain_communities(G, seed=42)
    partition = {}
    for i, comm in enumerate(communities):
        partition[i] = {str(n) for n in comm}
    return [partition]


def _build_community_prompt(names: list, types: list, edges: list, G: nx.Graph) -> str:
    parts = ["Entities in this community:"]
    for name, etype in zip(names, types):
        parts.append(f"  - {name} ({etype})")

    if edges:
        parts.append("\nRelationships:")
        for u, v, data in edges[:20]:
            src_name = G.nodes[u].get("name", u)
            tgt_name = G.nodes[v].get("name", v)
            parts.append(f"  - {src_name} --[{data.get('rel_type', '?')}]--> {tgt_name}")

    return "\n".join(parts)


def _summarize_community(prompt: str) -> str:
    try:
        response = batch_circuit.call(
            batch_llm.chat,
            messages=[{"role": "user", "content":
                       f"Summarize this knowledge graph community in 2-3 sentences. "
                       f"Focus on what connects these entities.\n\n{prompt}"}]
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Community summarization failed: {e}")
        return "Community summary unavailable."
