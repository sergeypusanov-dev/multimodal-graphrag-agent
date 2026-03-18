from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import yaml, time

config = yaml.safe_load(open("config.yaml"))

LLM_TOKENS  = Counter("llm_tokens_total","LLM tokens",["provider","role","direction"])
LLM_LATENCY = Histogram("llm_latency_ms","LLM latency",["provider"])
LLM_COST    = Counter("llm_cost_usd_total","Estimated cost USD",["provider","model"])
GRAPH_NODES = Gauge("kg_entities_total","Knowledge graph entities")
GRAPH_EDGES = Gauge("kg_relationships_total","Knowledge graph relationships")
AGENT_TASKS = Counter("agent_tasks_total","Agent tasks",["intent","status"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    from validate_config import validate_all
    validate_all()
    from cache.manager import patch_embedder_with_cache
    patch_embedder_with_cache()
    from utils.paths import get_watch_folder
    from tasks.watcher_wsl2 import get_observer, KnowledgeEventHandler
    supported = set()
    for exts in config["knowledge_base"]["supported_formats"].values():
        supported.update(exts)
    folder   = str(get_watch_folder())
    observer = get_observer(folder)
    observer.schedule(KnowledgeEventHandler(supported), folder, recursive=True)
    observer.start()
    yield
    observer.stop(); observer.join()

app = FastAPI(title="Multimodal GraphRAG Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
from security.middleware import setup_rate_limiting
setup_rate_limiting(app)
from a2a.agent_card import router as card_router
from a2a.server import router as a2a_router
app.include_router(card_router)
app.include_router(a2a_router)

from pydantic import BaseModel
from typing import Optional, List
from fastapi import UploadFile, File, Form
import asyncio

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/chat")
async def chat(req: ChatRequest,
               auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)):
    from agent.graph import run_agent
    start = time.time()
    try:
        answer = await asyncio.get_event_loop().run_in_executor(
            None, run_agent, req.message, [], req.session_id)
        AGENT_TASKS.labels(intent="chat",status="completed").inc()
        return {"answer":answer,"session_id":req.session_id,
                "latency_ms":int((time.time()-start)*1000)}
    except Exception as e:
        AGENT_TASKS.labels(intent="chat",status="failed").inc()
        raise

@app.post("/chat/multimodal")
async def chat_multimodal(
    message: str = Form(default="Describe the attached file(s)."),
    session_id: Optional[str] = Form(default=None),
    files: List[UploadFile] = File(default=[]),
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    import tempfile, os
    from agent.graph import run_agent
    uploaded, tmp_files = [], []
    for f in files:
        suffix = os.path.splitext(f.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await f.read()); tmp_files.append(tmp.name)
            uploaded.append({"path":tmp.name,"name":f.filename,"mime":f.content_type})
    try:
        answer = await asyncio.get_event_loop().run_in_executor(
            None, run_agent, message, uploaded, session_id)
        return {"answer":answer,"files_processed":len(uploaded)}
    finally:
        for p in tmp_files:
            try: os.unlink(p)
            except: pass

@app.get("/health")
async def health():
    from security.middleware import llm_circuit, qdrant_circuit
    return {"status":"ok","circuits":{"llm":llm_circuit.state,"qdrant":qdrant_circuit.state}}

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/admin/specialists")
async def get_specialists():
    from agent.orchestrator import SPECIALISTS
    return {"specialists": [
        {"key": k, "name": v["name"], "description": v["description"],
         "tools_count": len(v["tool_patterns"]),
         "tools": v["tool_patterns"],
         "keywords": v["keywords"],
         "system_prompt": v["system_prompt"]}
        for k, v in SPECIALISTS.items()
    ]}

@app.post("/admin/specialists/test")
async def test_specialist_routing(req: dict):
    from agent.orchestrator import classify_specialist, get_specialist_name, SPECIALISTS
    query = req.get("query", "")
    key = classify_specialist(query)
    scores = {}
    query_lower = query.lower()
    for k, spec in SPECIALISTS.items():
        scores[k] = sum(2 for kw in spec["keywords"] if kw in query_lower)
    return {
        "query": query,
        "selected": key,
        "specialist_name": get_specialist_name(key),
        "scores": scores
    }

@app.get("/admin/agent/prompt-preview")
async def preview_system_prompt():
    from agent.graph import build_system_prompt
    return {"prompt": build_system_prompt()}

@app.get("/admin/activity")
async def get_activity_log(limit: int = 50, session_id: Optional[str] = None):
    from database import get_db
    db = get_db()
    where = "WHERE session_id=%s" if session_id else ""
    params = ([session_id, limit] if session_id else [limit])
    rows = db.fetch(f"""SELECT id, session_id, step, specialist, tool_name, tool_args,
                               tool_result, duration_ms, created_at
                        FROM activity_log {where}
                        ORDER BY created_at DESC LIMIT %s""", params)
    for r in rows:
        for k in ("id", "created_at"):
            if r.get(k): r[k] = str(r[k])
    return {"entries": rows}

@app.delete("/admin/activity")
async def clear_activity_log(
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    db.execute("DELETE FROM activity_log")
    return {"status": "ok"}

@app.get("/kb/stats")
async def kb_stats():
    from database import get_db
    db = get_db()
    entities = db.fetchone("SELECT COUNT(*) as n FROM kg_entities")["n"]
    rels     = db.fetchone("SELECT COUNT(*) as n FROM kg_relationships")["n"]
    chunks   = db.fetchone("SELECT COUNT(*) as n FROM kg_chunks")["n"]
    files    = db.fetchone("SELECT COUNT(*) as n FROM kg_file_index WHERE status='indexed'")["n"]
    GRAPH_NODES.set(entities); GRAPH_EDGES.set(rels)
    return {"entities":entities,"relationships":rels,"chunks":chunks,"indexed_files":files}

@app.get("/kb/files")
async def kb_files(status: Optional[str] = None, limit: int = 100, offset: int = 0):
    from database import get_db
    db = get_db()
    where = "WHERE status=%s" if status else ""
    params = [status, limit, offset] if status else [limit, offset]
    sql = f"""SELECT id, file_path, file_hash, status, entity_count, chunk_count,
                     indexed_at, last_modified, error_msg
              FROM kg_file_index {where}
              ORDER BY indexed_at DESC NULLS LAST LIMIT %s OFFSET %s"""
    rows = db.fetch(sql, params)
    for r in rows:
        for k in ("indexed_at", "last_modified"):
            if r.get(k): r[k] = str(r[k])
        if r.get("id"): r["id"] = str(r["id"])
    total = db.fetchone(f"SELECT COUNT(*) as n FROM kg_file_index {where}",
                        [status] if status else [])["n"]
    return {"files": rows, "total": total}

@app.post("/kb/upload")
async def kb_upload(
    files: List[UploadFile] = File(...),
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    import os
    saved = []
    for f in files:
        dest = f"/data/knowledge/{f.filename}"
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(await f.read())
            saved.append({"filename": f.filename, "path": dest, "size": os.path.getsize(dest)})
        except PermissionError:
            from fastapi import HTTPException
            raise HTTPException(500, f"Permission denied writing to {dest}. Fix: docker exec -u root agent-api chown -R agent:agent /data/knowledge")
    return {"uploaded": len(saved), "files": saved}

@app.post("/kb/sync")
async def kb_sync(
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from tasks.watcher import sync_knowledge_folder
    task = sync_knowledge_folder.apply_async(queue="default")
    return {"task_id": task.id, "status": "queued"}

@app.get("/kb/entities")
async def kb_entities(limit: int = 50, offset: int = 0, search: Optional[str] = None):
    from database import get_db
    db = get_db()
    where = "WHERE name ILIKE %s OR type ILIKE %s" if search else ""
    params = ([f"%{search}%", f"%{search}%", limit, offset] if search
              else [limit, offset])
    rows = db.fetch(f"""SELECT id, name, type, description, media_type, created_at
                        FROM kg_entities {where}
                        ORDER BY created_at DESC LIMIT %s OFFSET %s""", params)
    for r in rows:
        if r.get("id"): r["id"] = str(r["id"])
        if r.get("created_at"): r["created_at"] = str(r["created_at"])
    return {"entities": rows}

# ═══════════════════════════════════════════════════════
# AGENT SETTINGS & RULES
# ═══════════════════════════════════════════════════════

@app.get("/admin/agent/settings")
async def get_agent_settings():
    from database import get_db
    db = get_db()
    row = db.fetchone("SELECT system_prompt, personality, language, updated_at FROM agent_settings WHERE id=1")
    if row and row.get("updated_at"): row["updated_at"] = str(row["updated_at"])
    return row or {"system_prompt": "", "personality": "", "language": ""}

class AgentSettingsUpdate(BaseModel):
    system_prompt: Optional[str] = None
    personality: Optional[str] = None
    language: Optional[str] = None

@app.put("/admin/agent/settings")
async def update_agent_settings(
    req: AgentSettingsUpdate,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    db.execute("""UPDATE agent_settings SET system_prompt=COALESCE(%s, system_prompt),
                  personality=COALESCE(%s, personality), language=COALESCE(%s, language),
                  updated_at=NOW() WHERE id=1""",
               [req.system_prompt, req.personality, req.language])
    return {"status": "ok"}

@app.get("/admin/agent/rules")
async def get_agent_rules():
    from database import get_db
    db = get_db()
    rows = db.fetch("SELECT id, rule_text, category, enabled, priority, created_at FROM agent_rules ORDER BY priority DESC, created_at")
    for r in rows:
        if r.get("id"): r["id"] = str(r["id"])
        if r.get("created_at"): r["created_at"] = str(r["created_at"])
    return {"rules": rows}

class AgentRuleCreate(BaseModel):
    rule_text: str
    category: str = "general"
    priority: int = 0

@app.post("/admin/agent/rules")
async def create_agent_rule(
    req: AgentRuleCreate,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    db.execute("INSERT INTO agent_rules (rule_text, category, priority) VALUES (%s, %s, %s)",
               [req.rule_text, req.category, req.priority])
    return {"status": "ok"}

class AgentRuleUpdate(BaseModel):
    rule_text: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None

@app.patch("/admin/agent/rules/{rule_id}")
async def update_agent_rule(
    rule_id: str,
    req: AgentRuleUpdate,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    if req.rule_text is not None:
        db.execute("UPDATE agent_rules SET rule_text=%s WHERE id=%s", [req.rule_text, rule_id])
    if req.enabled is not None:
        db.execute("UPDATE agent_rules SET enabled=%s WHERE id=%s", [req.enabled, rule_id])
    if req.priority is not None:
        db.execute("UPDATE agent_rules SET priority=%s WHERE id=%s", [req.priority, rule_id])
    return {"status": "ok"}

@app.delete("/admin/agent/rules/{rule_id}")
async def delete_agent_rule(
    rule_id: str,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    db.execute("DELETE FROM agent_rules WHERE id=%s", [rule_id])
    return {"status": "ok"}

# ═══════════════════════════════════════════════════════
# MCP SERVERS & TOOLS
# ═══════════════════════════════════════════════════════

@app.get("/admin/mcp/servers")
async def get_mcp_servers():
    from database import get_db
    db = get_db()
    servers = db.fetch("SELECT id, name, url, enabled, status, last_check, error_msg, created_at FROM mcp_servers ORDER BY created_at")
    for s in servers:
        for k in ("id", "last_check", "created_at"):
            if s.get(k): s[k] = str(s[k])
        tools = db.fetch("SELECT id, tool_name, description, enabled FROM mcp_tools WHERE server_id=%s", [s["id"]])
        for t in tools:
            if t.get("id"): t["id"] = str(t["id"])
        s["tools"] = tools
    return {"servers": servers}

class McpServerCreate(BaseModel):
    name: str
    url: str
    api_key: Optional[str] = None

@app.post("/admin/mcp/servers")
async def add_mcp_server(
    req: McpServerCreate,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    import uuid
    sid = str(uuid.uuid4())
    db.execute("INSERT INTO mcp_servers (id, name, url, api_key) VALUES (%s, %s, %s, %s)",
               [sid, req.name, req.url, req.api_key])
    # Try to discover tools
    tools = await _discover_mcp_tools(sid, req.url, req.api_key, db)
    return {"id": sid, "status": "ok", "tools_discovered": len(tools)}

@app.delete("/admin/mcp/servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    db.execute("DELETE FROM mcp_servers WHERE id=%s", [server_id])
    return {"status": "ok"}

@app.patch("/admin/mcp/servers/{server_id}")
async def update_mcp_server(
    server_id: str,
    req: dict,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    if "enabled" in req:
        db.execute("UPDATE mcp_servers SET enabled=%s WHERE id=%s", [req["enabled"], server_id])
    if "name" in req:
        db.execute("UPDATE mcp_servers SET name=%s WHERE id=%s", [req["name"], server_id])
    return {"status": "ok"}

@app.post("/admin/mcp/servers/{server_id}/refresh")
async def refresh_mcp_server(
    server_id: str,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    srv = db.fetchone("SELECT url, api_key FROM mcp_servers WHERE id=%s", [server_id])
    if not srv:
        from fastapi import HTTPException
        raise HTTPException(404, "Server not found")
    tools = await _discover_mcp_tools(server_id, srv["url"], srv.get("api_key"), db)
    return {"status": "ok", "tools_discovered": len(tools)}

@app.patch("/admin/mcp/tools/{tool_id}")
async def update_mcp_tool(
    tool_id: str,
    req: dict,
    auth=Depends(__import__("security.middleware",fromlist=["verify_auth"]).verify_auth)
):
    from database import get_db
    db = get_db()
    if "enabled" in req:
        db.execute("UPDATE mcp_tools SET enabled=%s WHERE id=%s", [req["enabled"], tool_id])
    return {"status": "ok"}

async def _discover_mcp_tools(server_id: str, url: str, api_key: str, db) -> list:
    """Connect to MCP server via SSE or HTTP and discover available tools."""
    import httpx, json, asyncio
    tools = []
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Detect transport: if URL ends with /sse, use SSE transport
        if url.rstrip("/").endswith("/sse"):
            tools = await _discover_via_sse(url, headers)
        else:
            tools = await _discover_via_http(url, headers)

        # Save tools to DB
        for t in tools:
            db.execute("""INSERT INTO mcp_tools (server_id, tool_name, description, input_schema)
                          VALUES (%s, %s, %s, %s)
                          ON CONFLICT (server_id, tool_name) DO UPDATE
                          SET description=%s, input_schema=%s""",
                       [server_id, t.get("name", ""), t.get("description", ""),
                        json.dumps(t.get("inputSchema", t.get("input_schema", {}))),
                        t.get("description", ""),
                        json.dumps(t.get("inputSchema", t.get("input_schema", {})))])

        status = "connected" if tools else "connected (no tools)"
        db.execute("UPDATE mcp_servers SET status=%s, last_check=NOW(), error_msg=NULL WHERE id=%s",
                   [status, server_id])
    except Exception as e:
        import traceback, logging
        logging.error(f"MCP discover error: {traceback.format_exc()}")
        db.execute("UPDATE mcp_servers SET status='error', last_check=NOW(), error_msg=%s WHERE id=%s",
                   [str(e)[:500], server_id])
    return tools


async def _discover_via_sse(url: str, headers: dict) -> list:
    """MCP SSE transport: full handshake — initialize, notifications/initialized, tools/list."""
    import aiohttp, json

    base_url = url.rsplit("/sse", 1)[0]
    # Add Host header for servers that validate it
    parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
    host_header = parsed.netloc
    if host_header:
        headers = {**headers, "Host": host_header}

    # Replace localhost with host.docker.internal for Docker compatibility
    docker_url = url.replace("://localhost", "://host.docker.internal")
    docker_base = docker_url.rsplit("/sse", 1)[0]

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(docker_url) as sse:
            ep = None
            initialized = False
            tools = []

            async for raw_line in sse.content:
                text = raw_line.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue

                if text.startswith("data: ") and "/messages/" in text and not ep:
                    ep = text[6:].strip()
                    # Step 1: initialize
                    await session.post(docker_base + ep, json={
                        "jsonrpc": "2.0", "method": "initialize", "id": 1,
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "graphrag-agent", "version": "1.0.0"}
                        }
                    })

                elif text.startswith("data: ") and ep:
                    data = text[6:].strip()
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    # Step 2: after initialize response, send initialized + tools/list
                    if msg.get("id") == 1 and "result" in msg and not initialized:
                        initialized = True
                        await session.post(docker_base + ep, json={
                            "jsonrpc": "2.0", "method": "notifications/initialized"
                        })
                        await session.post(docker_base + ep, json={
                            "jsonrpc": "2.0", "method": "tools/list", "id": 2
                        })

                    # Step 3: receive tools/list response
                    elif msg.get("id") == 2 and "result" in msg:
                        tools = msg["result"].get("tools", [])
                        return tools

    return []


async def _discover_via_http(url: str, headers: dict) -> list:
    """Try direct HTTP JSON-RPC endpoints."""
    import httpx, json

    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for endpoint in ["/tools/list", "/tools", "/api/tools", ""]:
            try:
                target = url.rstrip("/") + endpoint
                r = await client.post(target,
                                      json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                                      headers={"Content-Type": "application/json"})
                if r.status_code == 200:
                    data = r.json()
                    tool_list = data.get("result", {}).get("tools", data.get("tools", []))
                    if tool_list:
                        return tool_list
            except Exception:
                continue
    return []
