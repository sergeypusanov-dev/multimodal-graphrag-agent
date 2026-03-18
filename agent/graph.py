from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from typing import TypedDict, Annotated, Optional, List
import operator, yaml, os

config = yaml.safe_load(open("config.yaml"))

class AgentState(TypedDict):
    messages:         Annotated[List, operator.add]
    input_text:       str
    input_files:      List[dict]
    intent:           str
    query_mode:       str
    date_a:           Optional[str]
    date_b:           Optional[str]
    retrieved_chunks: List[dict]
    graph_context:    str
    media_context:    List[dict]
    final_answer:     str
    sources:          List[str]
    index_status:     Optional[dict]
    session_id:       str
    iterations:       int

def ingest_node(state: AgentState) -> dict:
    from security.middleware import sanitize_input
    from media.processor import process_file
    processed_files = []
    for f in state.get("input_files",[]):
        if f.get("path"):
            result = process_file(f["path"], config)
            processed_files.append({**f,**result})
    extra = "\n\n".join(f["content"] for f in processed_files if "content" in f)
    combined = sanitize_input(f"{state['input_text']}\n\n{extra}".strip() if extra else state["input_text"])
    return {"input_text":combined,"input_files":processed_files,"iterations":0}

def router_node(state: AgentState) -> dict:
    import json
    from llm.adapter import batch_llm
    from security.middleware import batch_circuit
    response = batch_circuit.call(
        batch_llm.chat,
        messages=[{"role":"user","content":
            f'Classify. Return JSON: {{"intent":"qa|research|index|temporal|compare",'
            f'"query_mode":"local|global|temporal|events",'
            f'"date_a":"ISO or null","date_b":"ISO or null"}}\nQuery: {state["input_text"][:400]}'}]
    )
    try:
        parsed = json.loads(response.text.strip())
    except Exception:
        parsed = {"intent":"qa","query_mode":"local","date_a":None,"date_b":None}
    return {k: parsed.get(k) for k in ["intent","query_mode","date_a","date_b"]}

def retrieval_node(state: AgentState) -> dict:
    from cache.manager import cache_mgr
    from vector_store.adapter import search_chunks
    query  = state["input_text"]
    cached = cache_mgr.get_semantic(query)
    if cached:
        return {"graph_context":cached,"retrieved_chunks":[]}
    chunks = search_chunks(query, top_k=20)
    from graph.query import build_graph_context
    ctx = build_graph_context(chunks, state.get("query_mode","local"), state.get("date_a"), state)
    return {"retrieved_chunks":chunks,"graph_context":ctx}

def temporal_node(state: AgentState) -> dict:
    from database import get_db
    from graph.temporal import get_graph_slice, compare_slices, get_entity_timeline
    from cache.manager import cache_mgr
    db  = get_db()
    key = f"{state.get('intent')}:{state.get('date_a')}:{state.get('date_b')}"
    cached = cache_mgr.get_graph(key)
    if cached: return {"graph_context":str(cached)}
    if state.get("intent") == "compare" and state.get("date_a") and state.get("date_b"):
        ctx = compare_slices(db, state["date_a"], state["date_b"])
    elif state.get("date_a"):
        ctx = get_graph_slice(db, state["date_a"])
    else:
        ctx = get_entity_timeline(db, state["input_text"])
    cache_mgr.set_graph(key, {"context":str(ctx)})
    return {"graph_context":str(ctx)}

def media_context_node(state: AgentState) -> dict:
    media_ctx = []
    for f in state.get("input_files",[]):
        if f.get("media_type") == "image" and f.get("raw_image_data"):
            media_ctx.append({"type":"image","data":f["raw_image_data"],
                              "media_type":f.get("image_media_type","image/jpeg")})
        elif f.get("media_type") in ("audio","video"):
            media_ctx.append({"type":"transcript","content":f.get("content",""),
                              "segments":f.get("segments",[])})
    return {"media_context":media_ctx}

def build_system_prompt() -> str:
    try:
        from database import get_db
        db = get_db()
        settings = db.fetchone("SELECT system_prompt, personality, language FROM agent_settings WHERE id=1")
        rules = db.fetch("SELECT rule_text FROM agent_rules WHERE enabled=TRUE ORDER BY priority DESC, created_at")
    except Exception:
        settings = None
        rules = []

    parts = []
    base = (settings or {}).get("system_prompt", "").strip() if settings else ""
    if base:
        parts.append(base)
    else:
        parts.append("You are a multimodal research assistant with a temporal knowledge graph. "
                      "Answer in the user's language. Cite [source: X] for every factual claim.")

    if settings and settings.get("personality"):
        parts.append(f"Personality: {settings['personality']}")
    if settings and settings.get("language"):
        parts.append(f"Language: {settings['language']}")

    if rules:
        parts.append("Rules you MUST follow:")
        for r in rules:
            parts.append(f"- {r['rule_text']}")

    return "\n\n".join(parts)

def synthesize_node(state: AgentState) -> dict:
    from llm.adapter import main_llm
    from security.middleware import llm_circuit
    from cache.manager import cache_mgr
    import json, logging

    images = [m["data"] for m in state.get("media_context",[]) if m.get("type")=="image"]
    system = build_system_prompt()
    user_text = (f"Knowledge graph context:\n{state.get('graph_context','No context.')}\n\n"
                 f"Query: {state['input_text']}")

    # Load MCP tools
    mcp_tools, mcp_tool_map = [], {}
    try:
        from mcp.client import get_enabled_mcp_tools
        mcp_tools, mcp_tool_map = get_enabled_mcp_tools()
    except Exception as e:
        logging.warning(f"Failed to load MCP tools: {e}")

    # Select relevant MCP tools (max 15 to stay within context limits)
    if mcp_tools and len(mcp_tools) <= 15:
        all_tools = mcp_tools
    elif mcp_tools:
        query_lower = state["input_text"].lower()
        # Detect server prefixes mentioned in query
        prefixes = set()
        keyword_map = {
            "wildberries": "wb_", "wb": "wb_", "вб": "wb_", "вайлдберриз": "wb_",
            "баланс": "balance", "продаж": "sales", "заказ": "order", "цен": "price",
            "склад": "stock", "warehouse": "warehouse", "поставк": "supply",
            "возврат": "return", "отчёт": "report", "отчет": "report",
            "карточ": "card", "товар": "product", "категори": "categor",
        }
        search_terms = set()
        for keyword, term in keyword_map.items():
            if keyword in query_lower:
                if term.endswith("_"):
                    prefixes.add(term)
                else:
                    search_terms.add(term)

        selected = []
        for t in mcp_tools:
            name = t["function"]["name"].lower()
            desc = (t["function"].get("description") or "").lower()
            # Include if prefix matches
            if any(name.startswith(p) for p in prefixes):
                # Further filter by search terms if any
                if search_terms:
                    if any(term in name or term in desc for term in search_terms):
                        selected.append(t)
                else:
                    selected.append(t)
            # Include if search term matches directly
            elif any(term in name or term in desc for term in search_terms):
                selected.append(t)

        all_tools = selected[:15] if selected else mcp_tools[:10]
    else:
        all_tools = None

    # Add tool usage instruction to system prompt
    if all_tools:
        tool_list = "\n".join(f"- {t['function']['name']}: {(t['function'].get('description') or '')[:80]}"
                               for t in all_tools)
        system += (f"\n\nYou have access to {len(all_tools)} external tools. "
                   "You MUST call the appropriate tool when the user asks for real-time data "
                   "like balance, sales, orders, prices, stocks, etc.\n"
                   f"Available tools:\n{tool_list}")

    # Build messages
    messages = [{"role": "user", "content": user_text}]

    # Tool call loop (max 5 iterations)
    answer = ""
    response = None
    for iteration in range(5):
        if images and iteration == 0:
            response = llm_circuit.call(main_llm.chat_with_vision, user_text, images, system)
        else:
            response = llm_circuit.call(main_llm.chat, messages, system, all_tools)

        print(f"[SYNTH] iter={iteration} tool_calls={response.tool_calls is not None} text_len={len(response.text or '')}", flush=True)

        # If no tool calls, we have the final answer
        if not response.tool_calls:
            answer = response.text
            break

        # Process tool calls
        print(f"[SYNTH] LLM requested {len(response.tool_calls)} tool call(s)", flush=True)

        # Add assistant message with tool calls (serialized)
        assistant_msg = {"role": "assistant", "content": response.text or "",
                         "tool_calls": [{"id": tc["id"], "type": "function",
                                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                                        for tc in response.tool_calls]}
        messages.append(assistant_msg)

        for tc in response.tool_calls:
            tool_name = tc["name"]
            try:
                args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except json.JSONDecodeError:
                args = {}

            print(f"[SYNTH] Executing: {tool_name}({json.dumps(args, ensure_ascii=False)[:100]})", flush=True)

            # Execute: MCP tool or local tool
            if tool_name in mcp_tool_map:
                from mcp.client import call_mcp_tool
                result = call_mcp_tool(tool_name, args, mcp_tool_map)
            else:
                from agent.tools import execute_tool
                result = execute_tool(tool_name, args)

            print(f"[SYNTH] Result: {str(result)[:200]}", flush=True)

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result)[:4000]
            })

        # Continue loop — LLM will process tool results
    else:
        answer = response.text if response else "Tool call limit reached."

    cache_mgr.set_semantic(state["input_text"], answer)
    return {
        "final_answer": answer,
        "messages": [{"role": "user", "content": state["input_text"]},
                     {"role": "assistant", "content": answer}],
        "iterations": state.get("iterations", 0) + 1,
    }

def index_node(state: AgentState) -> dict:
    from tasks.watcher import index_document
    statuses = []
    for f in state.get("input_files",[]):
        if f.get("path"):
            task = index_document.apply_async(args=[f["path"]], queue="indexing")
            statuses.append({"file":f["path"],"task_id":task.id})
    return {"index_status":{"queued":statuses},
            "final_answer":f"Поставлено в очередь: {len(statuses)} файлов"}

def route_intent(state: AgentState) -> str:
    intent = state.get("intent","qa")
    if intent == "index": return "index"
    if intent in ("temporal","compare"): return "temporal"
    if state.get("input_files"): return "media_context"
    return "retrieval"

def route_after_retrieval(state: AgentState) -> str:
    return "media_context" if state.get("input_files") else "synthesize"

builder = StateGraph(AgentState)
for name, fn in [("ingest",ingest_node),("router",router_node),("retrieval",retrieval_node),
                 ("temporal",temporal_node),("media_context",media_context_node),
                 ("synthesize",synthesize_node),("index",index_node)]:
    builder.add_node(name, fn)

builder.set_entry_point("ingest")
builder.add_edge("ingest","router")
builder.add_conditional_edges("router", route_intent,
    {"retrieval":"retrieval","temporal":"temporal","media_context":"media_context","index":"index"})
builder.add_conditional_edges("retrieval", route_after_retrieval,
    {"media_context":"media_context","synthesize":"synthesize"})
builder.add_edge("temporal","media_context")
builder.add_edge("media_context","synthesize")
builder.add_edge("synthesize",END)
builder.add_edge("index",END)

def _create_checkpointer():
    from psycopg import Connection
    conn = Connection.connect(os.environ["POSTGRES_URL"], autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return checkpointer

_checkpointer = _create_checkpointer()
agent_app = builder.compile(checkpointer=_checkpointer)

def run_agent(user_text: str, files: list = None, session_id: str = None) -> str:
    import uuid
    session_id = session_id or str(uuid.uuid4())
    result = agent_app.invoke(
        {"input_text":user_text,"input_files":files or [],"messages":[],"session_id":session_id},
        config={"configurable":{"thread_id":session_id}},
    )
    return result["final_answer"]
