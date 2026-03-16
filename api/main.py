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
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
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
