import asyncio, logging, yaml
from database import get_db
from vector_store.adapter import search_chunks
from graph.query import build_graph_context
from graph.temporal import get_entity_timeline, get_graph_slice, compare_slices
from graph.community import detect_communities
from a2a.client import a2a_client, DELEGATE_TOOL

logger = logging.getLogger(__name__)
config = yaml.safe_load(open("config.yaml"))

# ── Tool definitions for LLM tool_use ──────────────────────────────

KNOWLEDGE_SEARCH_TOOL = {
    "name": "knowledge_search",
    "description": "Search the temporal GraphRAG knowledge base. "
                   "Returns relevant chunks with entity and relationship context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query":      {"type": "string", "description": "Search query"},
            "top_k":      {"type": "integer", "description": "Number of results", "default": 10},
            "mode":       {"type": "string", "enum": ["local", "global", "temporal", "events"],
                           "default": "local"},
            "media_type": {"type": "string", "description": "Filter by media type (text/image/audio/video)"},
        },
        "required": ["query"],
    },
}

ENTITY_TIMELINE_TOOL = {
    "name": "entity_timeline",
    "description": "Get the full temporal history of an entity: "
                   "versions, events, and relationship changes over time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_name": {"type": "string", "description": "Entity name to look up"},
        },
        "required": ["entity_name"],
    },
}

GRAPH_SNAPSHOT_TOOL = {
    "name": "graph_snapshot",
    "description": "Get a snapshot of the knowledge graph at a specific date, "
                   "or compare two dates to see what changed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_a": {"type": "string", "description": "ISO date for snapshot or start of comparison"},
            "date_b": {"type": "string", "description": "ISO date for end of comparison (optional)"},
        },
        "required": ["date_a"],
    },
}

INDEX_DOCUMENT_TOOL = {
    "name": "index_document",
    "description": "Queue a document for indexing into the knowledge graph.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to index"},
        },
        "required": ["file_path"],
    },
}

COMMUNITY_DETECT_TOOL = {
    "name": "detect_communities",
    "description": "Run community detection on the knowledge graph to find clusters of related entities.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS = [
    KNOWLEDGE_SEARCH_TOOL,
    ENTITY_TIMELINE_TOOL,
    GRAPH_SNAPSHOT_TOOL,
    INDEX_DOCUMENT_TOOL,
    COMMUNITY_DETECT_TOOL,
    DELEGATE_TOOL,
]


# ── Tool execution ─────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "knowledge_search":
            return _tool_knowledge_search(tool_input)
        elif tool_name == "entity_timeline":
            return _tool_entity_timeline(tool_input)
        elif tool_name == "graph_snapshot":
            return _tool_graph_snapshot(tool_input)
        elif tool_name == "index_document":
            return _tool_index_document(tool_input)
        elif tool_name == "detect_communities":
            return _tool_detect_communities()
        elif tool_name == "delegate_to_agent":
            return _tool_delegate(tool_input)
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return f"Error executing {tool_name}: {e}"


def _tool_knowledge_search(inp: dict) -> str:
    query = inp["query"]
    top_k = inp.get("top_k", 10)
    mode = inp.get("mode", "local")
    filters = {}
    if inp.get("media_type"):
        filters["media_type"] = inp["media_type"]
    chunks = search_chunks(query, top_k=top_k, filters=filters or None)
    ctx = build_graph_context(chunks, mode)
    return ctx


def _tool_entity_timeline(inp: dict) -> str:
    db = get_db()
    result = get_entity_timeline(db, inp["entity_name"])
    return result.get("timeline", "No timeline data found.")


def _tool_graph_snapshot(inp: dict) -> str:
    db = get_db()
    date_a = inp["date_a"]
    date_b = inp.get("date_b")
    if date_b:
        result = compare_slices(db, date_a, date_b)
        return result.get("comparison", str(result))
    else:
        result = get_graph_slice(db, date_a)
        return result.get("slice", str(result))


def _tool_index_document(inp: dict) -> str:
    from tasks.watcher import index_document
    task = index_document.apply_async(args=[inp["file_path"]], queue="indexing")
    return f"Document queued for indexing. Task ID: {task.id}"


def _tool_detect_communities() -> str:
    communities = detect_communities()
    if not communities:
        return "No communities detected (not enough entities/relationships)."
    lines = [f"Detected {len(communities)} communities:"]
    for c in communities:
        lines.append(f"  - {c['title']} (level={c['level']}, entities={c['entity_count']}, "
                     f"rank={c['rank']:.1f})")
    return "\n".join(lines)


def _tool_delegate(inp: dict) -> str:
    agent_name = inp["agent_name"]
    task_text = inp["task"]
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run, a2a_client.send_task(agent_name, task_text)
                ).result(timeout=120)
        else:
            result = asyncio.run(a2a_client.send_task(agent_name, task_text))
        return result
    except Exception as e:
        return f"Delegation to {agent_name} failed: {e}"
