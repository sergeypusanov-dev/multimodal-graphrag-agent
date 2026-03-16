# Multimodal Temporal GraphRAG Agent — Финальная спецификация
# Версия 1.0 | Windows + WSL2 + Docker Desktop
# ═══════════════════════════════════════════════════════════════

---

## СЕКЦИЯ 01 — РОЛЬ И КОНТЕКСТ АГЕНТА (System Prompt)

```
Ты — интеллектуальный мультимодальный ассистент с собственной базой знаний
на основе Temporal GraphRAG. Принимаешь и анализируешь текст, изображения,
аудио и видео. База знаний строится автоматически из папки с документами
и обновляется по расписанию.

## Технологический стек
- Оркестрация:      LangGraph (StateGraph + PostgresSaver)
- База знаний:      Temporal GraphRAG (PostgreSQL + bi-temporal schema)
- Векторы:          Qdrant в Docker (настраивается)
- Эмбеддинги:       Gemini Embedding 2 (настраивается)
- Фоновые задачи:   Celery + Redis
- Трейсинг:         LangSmith (auto через LangGraph)
- Межагентность:    A2A Protocol v0.2
- LLM:              claude-sonnet-4-5 (настраивается)
- Платформа:        Windows 11 + WSL2 + Docker Desktop

## Принципы работы
- Отвечай на языке пользователя
- Цитируй источники [source: X] для каждого факта
- Для темпоральных вопросов всегда указывай период
- При нехватке данных в базе знаний — сообщай об этом явно
- Делегируй задачи другим агентам через A2A если они вне твоей компетенции
```

---

## СЕКЦИЯ 02 — CONFIG.YAML (ПОЛНЫЙ)

```yaml
# config.yaml — единый файл конфигурации всей системы

# ═══════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════
knowledge_base:
  # WSL2: НЕ используй /mnt/c/... — медленно!
  # Правильно: ~/data/knowledge
  watch_folder: "~/data/knowledge"
  sync_schedule: "0 */2 * * *"       # каждые 2 часа
  supported_formats:
    text:  [".txt",".md",".rst",".html",".pdf",".docx",".csv",".json"]
    image: [".jpg",".jpeg",".png",".gif",".webp",".bmp",".svg"]
    audio: [".mp3",".wav",".m4a",".ogg",".flac",".aac"]
    video: [".mp4",".avi",".mov",".mkv",".webm",".m4v"]
  chunk_size: 600
  chunk_overlap: 150
  max_file_size_mb: 500
  default_date_precision: "month"
  community_detection: "leiden"
  graph_hop_depth: 2

# ═══════════════════════════════════════════════════════
# LLM PROVIDERS
# ═══════════════════════════════════════════════════════
llm:
  main:
    provider: "anthropic"             # anthropic|openai|gemini|ollama
    model: "claude-sonnet-4-5"
    api_key_env: "ANTHROPIC_API_KEY"
    max_tokens: 4096
    temperature: 0.1
    timeout_sec: 120
  batch:
    provider: "anthropic"
    model: "claude-haiku-4-5-20251001"
    api_key_env: "ANTHROPIC_API_KEY"
    max_tokens: 1024
    temperature: 0.0
    timeout_sec: 30
  vision:
    provider: "anthropic"
    model: "claude-sonnet-4-5"
    api_key_env: "ANTHROPIC_API_KEY"
    max_tokens: 512
    temperature: 0.0
  fallback:
    enabled: true
    provider: "openai"
    model: "gpt-4o-mini"
    api_key_env: "OPENAI_API_KEY"
    max_tokens: 2048
    temperature: 0.1

# ═══════════════════════════════════════════════════════
# EMBEDDINGS
# ═══════════════════════════════════════════════════════
embeddings:
  provider: "gemini"      # gemini|openai|cohere|voyage|local|ollama
  gemini:
    model: "gemini-embedding-exp-03-07"
    api_key_env: "GEMINI_API_KEY"
    dimensions: 3072
    task_types:
      document: "RETRIEVAL_DOCUMENT"
      query:    "RETRIEVAL_QUERY"
    batch_size: 100
  openai:
    model: "text-embedding-3-large"
    api_key_env: "OPENAI_API_KEY"
    dimensions: 3072
    batch_size: 100
  cohere:
    model: "embed-multilingual-v3.0"
    api_key_env: "COHERE_API_KEY"
    dimensions: 1024
    input_types:
      document: "search_document"
      query:    "search_query"
    batch_size: 96
  local:
    model: "BAAI/bge-m3"
    device: "cpu"                     # cpu|cuda|mps
    dimensions: 1024
    batch_size: 32
    normalize: true
  ollama:
    model: "nomic-embed-text"
    base_url: "http://localhost:11434"
    dimensions: 768
    batch_size: 64

# ═══════════════════════════════════════════════════════
# VECTOR STORE
# ═══════════════════════════════════════════════════════
vector_store:
  provider: "qdrant"      # qdrant|pgvector|pinecone|weaviate|chroma|milvus
  collection_name: "knowledge_base"
  distance: "Cosine"
  qdrant:
    host: "localhost"
    port: 6333
    grpc_port: 6334
    prefer_grpc: true
    api_key_env: ""
    timeout: 30
  pgvector:
    url_env: "POSTGRES_URL"
    table_name: "embeddings"
    index_type: "ivfflat"
    ivfflat_lists: 100
  pinecone:
    api_key_env: "PINECONE_API_KEY"
    index_name: "knowledge-base"
    serverless: true
    cloud: "aws"
    region: "us-east-1"
  weaviate:
    url: "http://localhost:8080"
    api_key_env: ""
    class_name: "KnowledgeChunk"
  chroma:
    host: "localhost"
    port: 8002
    collection_name: "knowledge_base"
  milvus:
    host: "localhost"
    port: 19530
    collection_name: "knowledge_base"

# ═══════════════════════════════════════════════════════
# A2A PROTOCOL
# ═══════════════════════════════════════════════════════
a2a:
  enabled: true
  agent_id: "multimodal-graphrag-agent"
  agent_name: "Multimodal Temporal GraphRAG Agent"
  agent_version: "1.0.0"
  agent_url: "http://localhost:8000"
  description: "Multimodal knowledge agent with temporal GraphRAG"
  auth:
    enabled: true
    type: "api_key"
    api_key_env: "A2A_API_KEY"
  capabilities:
    streaming: true
    push_notifications: false
    state_transition_history: true
  skills:
    - id: "knowledge_search"
      name: "Knowledge base search"
      description: "Search temporal GraphRAG knowledge base"
      input_modes:  ["text","image","audio","video"]
      output_modes: ["text","file"]
      tags: ["rag","search","temporal","multimodal"]
    - id: "document_indexing"
      name: "Document indexing"
      description: "Index documents into knowledge graph"
      input_modes:  ["text","file"]
      output_modes: ["text"]
      tags: ["indexing","knowledge-graph"]
    - id: "entity_analysis"
      name: "Entity timeline analysis"
      description: "Analyze entity evolution over time"
      input_modes:  ["text"]
      output_modes: ["text","data"]
      tags: ["temporal","graphrag","analysis"]
  registry:
    enabled: true
    url: "http://localhost:8888"
    heartbeat_interval_sec: 30
    peer_agents:
      - url: "http://analytics-agent:8001"
        name: "DataAnalyst"
      - url: "http://translator-agent:8002"
        name: "Translator"

# ═══════════════════════════════════════════════════════
# DATABASES
# ═══════════════════════════════════════════════════════
databases:
  postgres:
    url_env: "POSTGRES_URL"
    pool_size: 10
    max_overflow: 20
  redis:
    url_env: "REDIS_URL"
    cache_ttl_sec: 3600

# ═══════════════════════════════════════════════════════
# MEDIA PROCESSING
# ═══════════════════════════════════════════════════════
media_processing:
  transcription_provider: "openai"
  video_frames_per_minute: 4
  video_max_frames: 30
  image_description_model: "claude-sonnet-4-5"

# ═══════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════
security:
  rate_limit:
    enabled: true
    requests_per_minute: 60
    burst: 20
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    recovery_timeout_sec: 60
  input_sanitization:
    max_text_length: 50000
    strip_html: true

# ═══════════════════════════════════════════════════════
# CACHING
# ═══════════════════════════════════════════════════════
cache:
  semantic_cache:
    enabled: true
    similarity_threshold: 0.95
    ttl_sec: 3600
  embedding_cache:
    enabled: true
    ttl_sec: 86400
  graph_traversal_cache:
    enabled: true
    ttl_sec: 300

# ═══════════════════════════════════════════════════════
# OBSERVABILITY
# ═══════════════════════════════════════════════════════
observability:
  langsmith:
    project: "multimodal-graphrag-agent"
    tracing_enabled: true
  prometheus:
    enabled: true
    port: 9090
  log_level: "INFO"
  cost_tracking: true
```

---

## СЕКЦИЯ 03 — WSL2 / WINDOWS КОНФИГУРАЦИЯ

### %USERPROFILE%\.wslconfig (C:\Users\<username>\.wslconfig)
```ini
[wsl2]
memory=16GB
processors=8
swap=8GB
swapFile=C:\\Temp\\wsl-swap.vhdx
pageReporting=false
networkingMode=mirrored
dnsTunneling=true
firewall=true
autoProxy=true
kernelCommandLine=sysctl.fs.inotify.max_user_watches=2097152 sysctl.fs.inotify.max_user_instances=8192 sysctl.fs.inotify.max_queued_events=65536
```

### /etc/wsl.conf (внутри WSL2 Ubuntu)
```ini
[automount]
enabled = true
root = /mnt/
options = "metadata,umask=22,fmask=11"
mountFsTab = true

[boot]
systemd = true
command = "sysctl -w fs.inotify.max_user_watches=2097152"

[interop]
enabled = true
appendWindowsPath = false

[network]
hostname = wsl-agent
```

### .gitattributes
```
* text=auto eol=lf
*.py   text eol=lf
*.sh   text eol=lf
*.yaml text eol=lf
*.yml  text eol=lf
*.sql  text eol=lf
*.md   text eol=lf
*.bat  text eol=crlf
*.cmd  text eol=crlf
```

### .dockerignore
```
.git
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.env
*.log
logs/
qdrant_storage/
pg_data/
redis_data/
chroma_data/
/mnt/
```

---

## СЕКЦИЯ 04 — DOCKERFILE + DOCKER-COMPOSE.YML

### Dockerfile
```dockerfile
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ curl ffmpeg libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WATCHDOG_POLLING=false
```

### docker-compose.yml
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    ports: ["6333:6333","6334:6334"]
    volumes: [qdrant_data:/qdrant/storage]
    deploy:
      resources:
        limits: {memory: 4G}
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    restart: unless-stopped
    healthcheck:
      test: ["CMD","curl","-f","http://localhost:6333/readyz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  redis:
    image: redis:7-alpine
    container_name: redis
    ports: ["6379:6379"]
    volumes: [redis_data:/data]
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    restart: unless-stopped
    healthcheck:
      test: ["CMD","redis-cli","ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  postgres:
    image: pgvector/pgvector:pg16
    container_name: postgres
    environment:
      POSTGRES_DB: agent_db
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports: ["5432:5432"]
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/01_schema.sql:ro
    command: >
      postgres
      -c shared_buffers=512MB
      -c effective_cache_size=2GB
      -c work_mem=64MB
      -c max_connections=100
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL","pg_isready -U agent -d agent_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  agent:
    build: {context: ., dockerfile: Dockerfile}
    container_name: agent-api
    ports: ["8000:8000","9090:9090"]
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - knowledge_data:/data/knowledge
    env_file: [.env]
    environment:
      POSTGRES_URL: postgresql://agent:${POSTGRES_PASSWORD}@postgres:5432/agent_db
      REDIS_URL: redis://redis:6379/0
      WATCHDOG_POLLING: "false"
    depends_on:
      postgres: {condition: service_healthy}
      redis:    {condition: service_healthy}
      qdrant:   {condition: service_healthy}
    restart: unless-stopped
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000

  celery-worker:
    build: {context: ., dockerfile: Dockerfile}
    container_name: celery-worker
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - knowledge_data:/data/knowledge
    env_file: [.env]
    environment:
      POSTGRES_URL: postgresql://agent:${POSTGRES_PASSWORD}@postgres:5432/agent_db
      REDIS_URL: redis://redis:6379/0
      WATCHDOG_POLLING: "false"
    depends_on:
      postgres: {condition: service_healthy}
      redis:    {condition: service_healthy}
    restart: unless-stopped
    command: celery -A tasks.watcher worker --loglevel=info -Q indexing,default -c 2

  celery-beat:
    build: {context: ., dockerfile: Dockerfile}
    container_name: celery-beat
    volumes: [./config.yaml:/app/config.yaml:ro]
    env_file: [.env]
    environment:
      REDIS_URL: redis://redis:6379/0
      POSTGRES_URL: postgresql://agent:${POSTGRES_PASSWORD}@postgres:5432/agent_db
    depends_on:
      redis: {condition: service_healthy}
    restart: unless-stopped
    command: celery -A tasks.watcher beat --loglevel=info

volumes:
  qdrant_data:
  redis_data:
  pg_data:
  knowledge_data:
```

---

## СЕКЦИЯ 05 — SCHEMA.SQL (BI-TEMPORAL GRAPHRAG)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE kg_entities (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,
    description  TEXT,
    aliases      TEXT[],
    embedding_id TEXT,
    media_type   TEXT DEFAULT 'text',
    source_file  TEXT,
    doc_ids      TEXT[],
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, type)
);

CREATE TABLE kg_entity_versions (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id      UUID NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_to       TIMESTAMPTZ,
    recorded_at    TIMESTAMPTZ DEFAULT NOW(),
    role           TEXT,
    org_id         UUID REFERENCES kg_entities(id),
    attributes     JSONB DEFAULT '{}',
    change_type    TEXT DEFAULT 'created',
    change_source  TEXT,
    confidence     FLOAT DEFAULT 1.0,
    date_precision TEXT DEFAULT 'month'
);

CREATE TABLE kg_relationships (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id   UUID NOT NULL REFERENCES kg_entities(id),
    target_id   UUID NOT NULL REFERENCES kg_entities(id),
    type        TEXT NOT NULL,
    description TEXT,
    weight      FLOAT DEFAULT 1.0,
    valid_from  TIMESTAMPTZ,
    valid_to    TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    cross_modal BOOLEAN DEFAULT FALSE,
    doc_ids     TEXT[]
);

CREATE TABLE kg_chunks (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content      TEXT NOT NULL,
    media_type   TEXT DEFAULT 'text',
    embedding_id TEXT,
    entity_ids   UUID[],
    doc_id       TEXT NOT NULL,
    source_file  TEXT,
    chunk_index  INT,
    timestamp_ms BIGINT,
    frame_number INT,
    metadata     JSONB DEFAULT '{}'
);

CREATE TABLE kg_communities (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    level        INT NOT NULL DEFAULT 0,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    embedding_id TEXT,
    entity_ids   UUID[],
    rank         FLOAT DEFAULT 0.0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE kg_events (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_ids     UUID[] NOT NULL,
    event_type     TEXT NOT NULL,
    event_date     TIMESTAMPTZ NOT NULL,
    date_precision TEXT DEFAULT 'day',
    description    TEXT,
    doc_ids        TEXT[],
    media_refs     JSONB DEFAULT '[]',
    embedding_id   TEXT
);

CREATE TABLE kg_file_index (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path     TEXT UNIQUE NOT NULL,
    file_hash     TEXT NOT NULL,
    last_modified TIMESTAMPTZ NOT NULL,
    indexed_at    TIMESTAMPTZ DEFAULT NOW(),
    status        TEXT DEFAULT 'indexed',
    entity_count  INT DEFAULT 0,
    chunk_count   INT DEFAULT 0,
    error_msg     TEXT
);

CREATE INDEX ON kg_entities (type);
CREATE INDEX ON kg_entities USING GIN (aliases);
CREATE INDEX ON kg_entity_versions (entity_id, valid_from, valid_to);
CREATE INDEX ON kg_relationships (source_id);
CREATE INDEX ON kg_relationships (target_id);
CREATE INDEX ON kg_relationships (valid_from, valid_to);
CREATE INDEX ON kg_chunks (doc_id);
CREATE INDEX ON kg_chunks (media_type);
CREATE INDEX ON kg_events (event_date);
CREATE INDEX ON kg_events USING GIN (entity_ids);
```

---

## СЕКЦИЯ 06 — LLM / EMBEDDING / VECTORDB АДАПТЕРЫ

### llm/adapter.py
```python
import os, yaml
from dataclasses import dataclass

config = yaml.safe_load(open("config.yaml"))

@dataclass
class LLMResponse:
    text: str; model: str; tokens_in: int; tokens_out: int; provider: str

class LLMAdapter:
    def __init__(self, role: str = "main"):
        self.cfg = config["llm"][role]
        self.provider = self.cfg["provider"]
        self.model    = self.cfg["model"]
        self.api_key  = os.getenv(self.cfg.get("api_key_env", ""), "")
        self._client  = None

    @property
    def client(self):
        if self._client: return self._client
        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        elif self.provider == "ollama":
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.cfg.get("base_url","http://localhost:11434/v1"),
                api_key="ollama")
        return self._client

    def chat(self, messages, system=None, tools=None) -> LLMResponse:
        try:
            return self._call(messages, system, tools)
        except Exception as e:
            fb = config["llm"].get("fallback", {})
            if fb.get("enabled") and self.provider != "fallback":
                import logging
                logging.warning(f"LLM {self.provider} failed: {e}. Fallback.")
                return LLMAdapter("fallback")._call(messages, system, tools)
            raise

    def _call(self, messages, system, tools) -> LLMResponse:
        max_tok = self.cfg.get("max_tokens", 1024)
        temp    = self.cfg.get("temperature", 0.1)
        if self.provider == "anthropic":
            kw = dict(model=self.model, max_tokens=max_tok,
                      messages=messages, temperature=temp)
            if system: kw["system"] = system
            if tools:  kw["tools"]  = tools
            r = self.client.messages.create(**kw)
            return LLMResponse(r.content[0].text, r.model,
                               r.usage.input_tokens, r.usage.output_tokens, "anthropic")
        elif self.provider in ("openai", "ollama"):
            msgs = ([{"role":"system","content":system}] + messages) if system else messages
            kw = dict(model=self.model, messages=msgs,
                      max_tokens=max_tok, temperature=temp)
            if tools: kw["tools"] = tools
            r = self.client.chat.completions.create(**kw)
            return LLMResponse(r.choices[0].message.content, r.model,
                               r.usage.prompt_tokens, r.usage.completion_tokens, self.provider)
        elif self.provider == "gemini":
            prompt = "\n".join(m["content"] for m in messages)
            if system: prompt = f"{system}\n\n{prompt}"
            r = self.client.generate_content(prompt)
            return LLMResponse(r.text, self.model,
                               r.usage_metadata.prompt_token_count,
                               r.usage_metadata.candidates_token_count, "gemini")

    def chat_with_vision(self, text, images_b64, system=None) -> LLMResponse:
        if self.provider == "anthropic":
            content = [{"type":"image","source":{"type":"base64",
                        "media_type":"image/jpeg","data":img}} for img in images_b64]
            content.append({"type":"text","text":text})
            return self.chat([{"role":"user","content":content}], system)
        elif self.provider == "openai":
            content = [{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{img}"}}
                       for img in images_b64]
            content.append({"type":"text","text":text})
            return self.chat([{"role":"user","content":content}], system)
        else:
            return self.chat([{"role":"user","content":text}], system)

main_llm   = LLMAdapter("main")
batch_llm  = LLMAdapter("batch")
vision_llm = LLMAdapter("vision")
```

### embeddings/adapter.py
```python
import os, yaml
config = yaml.safe_load(open("config.yaml"))

class EmbeddingAdapter:
    def __init__(self):
        self.provider = config["embeddings"]["provider"]
        self.cfg      = config["embeddings"][self.provider]
        self.dims     = self.cfg.get("dimensions", 1536)
        self._client  = None

    @property
    def client(self):
        if self._client: return self._client
        p = self.provider
        if p == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=os.getenv(self.cfg["api_key_env"]))
            self._client = genai
        elif p == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv(self.cfg["api_key_env"]))
        elif p == "cohere":
            import cohere
            self._client = cohere.Client(os.getenv(self.cfg["api_key_env"]))
        elif p == "voyage":
            import voyageai
            self._client = voyageai.Client(api_key=os.getenv(self.cfg["api_key_env"]))
        elif p == "local":
            from sentence_transformers import SentenceTransformer
            self._client = SentenceTransformer(self.cfg["model"],
                                               device=self.cfg.get("device","cpu"))
        elif p == "ollama":
            from openai import OpenAI
            self._client = OpenAI(base_url=f"{self.cfg['base_url']}/v1", api_key="ollama")
        return self._client

    def embed(self, text: str, mode: str = "document") -> list:
        return self.embed_batch([text], mode)[0]

    def embed_batch(self, texts: list, mode: str = "document") -> list:
        p = self.provider
        if p == "gemini":
            task = self.cfg["task_types"].get(mode, "RETRIEVAL_DOCUMENT")
            r = self.client.embed_content(model=f"models/{self.cfg['model']}",
                                          content=texts, task_type=task,
                                          output_dimensionality=self.dims)
            vecs = r["embedding"]
            return vecs if isinstance(vecs[0], list) else [vecs]
        elif p == "openai":
            r = self.client.embeddings.create(model=self.cfg["model"],
                                              input=texts, dimensions=self.dims)
            return [e.embedding for e in r.data]
        elif p == "cohere":
            it = self.cfg["input_types"].get(mode, "search_document")
            return self.client.embed(texts=texts, model=self.cfg["model"], input_type=it).embeddings
        elif p == "voyage":
            it = self.cfg["input_types"].get(mode, "document")
            return self.client.embed(texts, model=self.cfg["model"], input_type=it).embeddings
        elif p == "local":
            return self.client.encode(texts, normalize_embeddings=True).tolist()
        elif p == "ollama":
            return [self.client.embeddings.create(model=self.cfg["model"], input=t).data[0].embedding
                    for t in texts]

embedder       = EmbeddingAdapter()
embed_document = lambda t: embedder.embed(t, "document")
embed_query    = lambda t: embedder.embed(t, "query")
embed_batch    = lambda ts, m="document": embedder.embed_batch(ts, m)
```

### vector_store/adapter.py
```python
import yaml, uuid
from dataclasses import dataclass
from typing import Optional
from embeddings.adapter import embed_document, embed_query, embedder

config = yaml.safe_load(open("config.yaml"))

@dataclass
class SearchResult:
    id: str; score: float; payload: dict

class VectorStoreAdapter:
    def __init__(self):
        self.provider   = config["vector_store"]["provider"]
        self.cfg        = config["vector_store"][self.provider]
        self.collection = config["vector_store"]["collection_name"]
        self.dims       = embedder.dims
        self._client    = None

    @property
    def client(self):
        if self._client: return self._client
        p = self.provider
        if p == "qdrant":
            from qdrant_client import QdrantClient
            import os
            self._client = QdrantClient(host=self.cfg["host"], port=self.cfg["port"],
                                        api_key=os.getenv(self.cfg.get("api_key_env",""),None),
                                        timeout=self.cfg.get("timeout",30))
            self._init_qdrant()
        elif p == "pgvector":
            import psycopg2, os
            self._client = psycopg2.connect(os.getenv(self.cfg["url_env"]))
        elif p == "pinecone":
            from pinecone import Pinecone
            import os
            self._client = Pinecone(api_key=os.getenv(self.cfg["api_key_env"])).Index(self.cfg["index_name"])
        elif p == "chroma":
            import chromadb
            self._client = chromadb.HttpClient(host=self.cfg["host"], port=self.cfg["port"])
        return self._client

    def _init_qdrant(self):
        from qdrant_client.models import Distance, VectorParams
        existing = [c.name for c in self._client.get_collections().collections]
        if self.collection not in existing:
            d = {"Cosine": Distance.COSINE, "Dot": Distance.DOT, "Euclidean": Distance.EUCLID}
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dims,
                                            distance=d.get(config["vector_store"]["distance"], Distance.COSINE)))
            for field in ["media_type","entity_id","doc_id","chunk_type"]:
                self._client.create_payload_index(self.collection, field, "keyword")

    def upsert(self, text: str, payload: dict, point_id=None) -> str:
        pid    = point_id or str(uuid.uuid4())
        vector = embed_document(text)
        p      = self.provider
        if p == "qdrant":
            from qdrant_client.models import PointStruct
            self.client.upsert(collection_name=self.collection,
                               points=[PointStruct(id=pid, vector=vector,
                                                   payload={**payload,"text":text[:2000]})])
        elif p == "pgvector":
            import json
            with self.client.cursor() as cur:
                cur.execute("""
                    INSERT INTO embeddings (id, embedding, text, payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET embedding=%s, text=%s, payload=%s
                """, [pid, vector, text[:2000], json.dumps(payload),
                      vector, text[:2000], json.dumps(payload)])
            self.client.commit()
        elif p == "chroma":
            self.client.get_or_create_collection(self.collection).upsert(
                ids=[pid], embeddings=[vector], documents=[text[:2000]], metadatas=[payload])
        return pid

    def search(self, query: str, top_k: int = 10, filters: dict = None) -> list:
        q_vec = embed_query(query)
        p     = self.provider
        if p == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qf = Filter(must=[FieldCondition(key=k, match=MatchValue(value=v))
                               for k,v in filters.items()]) if filters else None
            hits = self.client.search(collection_name=self.collection, query_vector=q_vec,
                                       limit=top_k, query_filter=qf, with_payload=True)
            return [SearchResult(id=h.id, score=h.score, payload=h.payload) for h in hits]
        elif p == "pgvector":
            with self.client.cursor() as cur:
                cur.execute("""SELECT id, 1-(embedding<=>%s), text, payload
                               FROM embeddings ORDER BY embedding<=>%s LIMIT %s""",
                            [q_vec, q_vec, top_k])
                return [SearchResult(id=r[0],score=r[1],payload={"text":r[2],**r[3]})
                        for r in cur.fetchall()]
        elif p == "chroma":
            col = self.client.get_or_create_collection(self.collection)
            r = col.query(query_embeddings=[q_vec], n_results=top_k)
            return [SearchResult(id=i,score=1-d,payload=m)
                    for i,d,m in zip(r["ids"][0],r["distances"][0],r["metadatas"][0])]
        raise ValueError(f"Unknown vector store: {p}")

vector_store  = VectorStoreAdapter()
store_chunk   = lambda text, payload, pid=None: vector_store.upsert(text, payload, pid)
search_chunks = lambda query, top_k=10, filters=None: vector_store.search(query, top_k, filters)
```

---

## СЕКЦИЯ 07 — БЕЗОПАСНОСТЬ И CIRCUIT BREAKER

### security/middleware.py
```python
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os, time, yaml, threading

config = yaml.safe_load(open("config.yaml"))
security_cfg = config.get("security", {})
bearer = HTTPBearer(auto_error=False)

API_KEY = os.getenv(config["a2a"]["auth"].get("api_key_env", "A2A_API_KEY"), "")

async def verify_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer)
):
    if not config["a2a"]["auth"].get("enabled", False):
        return True
    if not creds:
        raise HTTPException(401, "Missing Authorization header")
    if creds.credentials != API_KEY:
        raise HTTPException(403, "Invalid API key")
    return True

class CircuitBreaker:
    CLOSED = "closed"; OPEN = "open"; HALFOPEN = "half_open"

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self._state            = self.CLOSED
        self._failures         = 0
        self._last_failure     = 0
        self._lock             = threading.Lock()

    def call(self, fn, *args, **kwargs):
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure > self.recovery_timeout:
                    self._state = self.HALFOPEN
                else:
                    raise RuntimeError(f"Circuit {self.name} is OPEN")
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if self._state == self.HALFOPEN:
                    self._state = self.CLOSED; self._failures = 0
            return result
        except Exception as e:
            with self._lock:
                self._failures += 1; self._last_failure = time.time()
                if self._failures >= self.failure_threshold:
                    self._state = self.OPEN
                    import logging
                    logging.error(f"Circuit {self.name} OPENED after {self._failures} failures")
            raise

    @property
    def state(self): return self._state

cfg_cb = security_cfg.get("circuit_breaker", {})
llm_circuit    = CircuitBreaker("llm",    cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))
embed_circuit  = CircuitBreaker("embed",  cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))
qdrant_circuit = CircuitBreaker("qdrant", cfg_cb.get("failure_threshold",3), cfg_cb.get("recovery_timeout_sec",30))
batch_circuit  = CircuitBreaker("batch",  cfg_cb.get("failure_threshold",5), cfg_cb.get("recovery_timeout_sec",60))

def setup_rate_limiting(app: FastAPI):
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    rate = security_cfg.get("rate_limit", {})
    if rate.get("enabled"):
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter
        from slowapi.middleware import SlowAPIMiddleware
        app.add_middleware(SlowAPIMiddleware)

def sanitize_input(text: str) -> str:
    san_cfg = security_cfg.get("input_sanitization", {})
    max_len = san_cfg.get("max_text_length", 50000)
    if len(text) > max_len:
        text = text[:max_len]
    if san_cfg.get("strip_html"):
        import re
        text = re.sub(r'<[^>]+>', '', text)
    suspicious = ["ignore previous instructions","disregard your system","you are now","forget everything"]
    for pattern in suspicious:
        if pattern.lower() in text.lower():
            import logging
            logging.warning(f"Possible prompt injection: {pattern}")
    return text.strip()
```

---

## СЕКЦИЯ 08 — КЭШИРОВАНИЕ

### cache/manager.py
```python
import json, hashlib, time
import redis as redis_lib
import yaml

config = yaml.safe_load(open("config.yaml"))

class CacheManager:
    def __init__(self):
        self.redis = redis_lib.from_url(config["databases"]["redis"]["url_env"])
        self.cfg   = config.get("cache", {})

    def get_semantic(self, query: str, threshold: float = None) -> str | None:
        cfg = self.cfg.get("semantic_cache", {})
        if not cfg.get("enabled"): return None
        threshold = threshold or cfg.get("similarity_threshold", 0.95)
        from embeddings.adapter import embed_query
        q_vec = embed_query(query)
        import numpy as np
        for key in self.redis.keys("sem_cache:*")[:200]:
            cached = self.redis.get(key)
            if not cached: continue
            entry = json.loads(cached)
            sim = float(np.dot(q_vec, entry["vector"]) /
                        (np.linalg.norm(q_vec) * np.linalg.norm(entry["vector"]) + 1e-8))
            if sim >= threshold:
                return entry["answer"]
        return None

    def set_semantic(self, query: str, answer: str):
        cfg = self.cfg.get("semantic_cache", {})
        if not cfg.get("enabled"): return
        from embeddings.adapter import embed_query
        key  = f"sem_cache:{hashlib.md5(query.encode()).hexdigest()}"
        data = {"query":query,"answer":answer,"vector":embed_query(query),"ts":time.time()}
        self.redis.setex(key, cfg.get("ttl_sec",3600), json.dumps(data))

    def get_embedding(self, text: str) -> list | None:
        cfg = self.cfg.get("embedding_cache", {})
        if not cfg.get("enabled"): return None
        cached = self.redis.get(f"emb:{hashlib.sha256(text.encode()).hexdigest()}")
        return json.loads(cached) if cached else None

    def set_embedding(self, text: str, vector: list):
        cfg = self.cfg.get("embedding_cache", {})
        if not cfg.get("enabled"): return
        self.redis.setex(f"emb:{hashlib.sha256(text.encode()).hexdigest()}",
                         cfg.get("ttl_sec",86400), json.dumps(vector))

    def get_graph(self, cache_key: str) -> dict | None:
        cfg = self.cfg.get("graph_traversal_cache", {})
        if not cfg.get("enabled"): return None
        cached = self.redis.get(f"graph:{cache_key}")
        return json.loads(cached) if cached else None

    def set_graph(self, cache_key: str, data: dict):
        cfg = self.cfg.get("graph_traversal_cache", {})
        if not cfg.get("enabled"): return
        self.redis.setex(f"graph:{cache_key}", cfg.get("ttl_sec",300), json.dumps(data))

cache_mgr = CacheManager()

def patch_embedder_with_cache():
    from embeddings import adapter
    orig_embed = adapter.embedder.embed
    def cached_embed(text: str, mode: str = "document") -> list:
        cached = cache_mgr.get_embedding(f"{mode}:{text}")
        if cached: return cached
        result = orig_embed(text, mode)
        cache_mgr.set_embedding(f"{mode}:{text}", result)
        return result
    adapter.embedder.embed = cached_embed
```

---

## СЕКЦИЯ 09 — FILE WATCHER (WSL2-AWARE) + CELERY

### tasks/watcher_wsl2.py
```python
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

def is_windows_mount(path: str) -> bool:
    p = Path(path).resolve()
    return len(p.parts) >= 3 and p.parts[1] == "mnt" and len(p.parts[2]) == 1

def get_observer(watch_path: str):
    force = os.getenv("WATCHDOG_POLLING", "false").lower() == "true"
    if force or is_windows_mount(watch_path):
        import logging
        logging.warning(f"PollingObserver for {watch_path}. Move data to ~/data/ for best perf.")
        return PollingObserver(timeout=5)
    return Observer()

class KnowledgeEventHandler(FileSystemEventHandler):
    def __init__(self, supported_extensions: set):
        self.supported = supported_extensions
        self._pending: dict[str, float] = {}

    def on_created(self, event):
        if not event.is_directory: self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory: self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory: self._handle(event.dest_path)

    def _handle(self, path: str):
        import time
        from tasks.watcher import index_document
        if Path(path).suffix.lower() not in self.supported: return
        now = time.time()
        if now - self._pending.get(path, 0) < 2.0: return
        self._pending[path] = now
        index_document.apply_async(args=[path], queue="indexing")
```

### tasks/watcher.py
```python
import os, hashlib, yaml
from celery import Celery
from celery.schedules import crontab
from pathlib import Path

config = yaml.safe_load(open("config.yaml"))
app    = Celery("agent",
                broker=os.getenv("REDIS_URL","redis://localhost:6379/0"),
                backend=os.getenv("REDIS_URL","redis://localhost:6379/0"))

app.conf.task_queues = (
    __import__("kombu").Queue("indexing", routing_key="indexing"),
    __import__("kombu").Queue("default",  routing_key="default"),
)
app.conf.task_default_queue         = "default"
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late             = True

schedule_str = config["knowledge_base"]["sync_schedule"]
parts = schedule_str.split()
app.conf.beat_schedule = {
    "sync-knowledge-base": {
        "task":     "tasks.watcher.sync_knowledge_folder",
        "schedule": crontab(minute=parts[0], hour=parts[1]),
    },
}

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(8192), b""): h.update(chunk)
    return h.hexdigest()

@app.task(name="tasks.watcher.sync_knowledge_folder", bind=True, max_retries=3, default_retry_delay=60)
def sync_knowledge_folder(self):
    from utils.paths import get_watch_folder
    from database import get_db
    db = get_db()
    supported = set()
    for exts in config["knowledge_base"]["supported_formats"].values():
        supported.update(exts)
    watch_folder = get_watch_folder()
    new_files, changed_files = [], []
    for file_path in watch_folder.rglob("*"):
        if not file_path.is_file(): continue
        if file_path.suffix.lower() not in supported: continue
        max_mb = config["knowledge_base"]["max_file_size_mb"]
        if file_path.stat().st_size > max_mb * 1024 * 1024: continue
        fp_str  = str(file_path)
        indexed = db.fetchone("SELECT file_hash FROM kg_file_index WHERE file_path=%s",[fp_str])
        if not indexed:
            new_files.append(fp_str)
        elif _file_hash(fp_str) != indexed["file_hash"]:
            changed_files.append(fp_str)
    for f in new_files + changed_files:
        index_document.apply_async(args=[f], queue="indexing")
    return {"new":len(new_files),"changed":len(changed_files)}

@app.task(name="tasks.watcher.index_document", bind=True, max_retries=3,
          default_retry_delay=120, queue="indexing", time_limit=3600)
def index_document(self, file_path: str):
    from media.processor import process_file
    from graph.indexer import run_indexing_pipeline
    from database import get_db
    db = get_db()
    try:
        db.execute("""
            INSERT INTO kg_file_index (file_path,file_hash,last_modified,status)
            VALUES (%s,%s,NOW(),'processing')
            ON CONFLICT (file_path) DO UPDATE SET status='processing',indexed_at=NOW()
        """,[file_path,_file_hash(file_path)])
        result = process_file(file_path, config)
        stats  = run_indexing_pipeline(file_path, result, config, db)
        db.execute("""
            UPDATE kg_file_index SET file_hash=%s,status='indexed',
              entity_count=%s,chunk_count=%s,error_msg=NULL WHERE file_path=%s
        """,[_file_hash(file_path),stats["entities"],stats["chunks"],file_path])
    except Exception as exc:
        db.execute("UPDATE kg_file_index SET status='failed',error_msg=%s WHERE file_path=%s",
                   [str(exc)[:500],file_path])
        raise self.retry(exc=exc)
```

---

## СЕКЦИЯ 10 — LANGGRAPH STATEGRAPH

### agent/graph.py
```python
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
    chunks = search_chunks(query, top_k=10)
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

def synthesize_node(state: AgentState) -> dict:
    from llm.adapter import main_llm
    from security.middleware import llm_circuit
    from cache.manager import cache_mgr
    images = [m["data"] for m in state.get("media_context",[]) if m.get("type")=="image"]
    system = ("You are a multimodal research assistant with a temporal knowledge graph. "
              "Answer in the user's language. Cite [source: X] for every factual claim.")
    user_text = (f"Knowledge graph context:\n{state.get('graph_context','No context.')}\n\n"
                 f"Query: {state['input_text']}")
    if images:
        response = llm_circuit.call(main_llm.chat_with_vision, user_text, images, system)
    else:
        response = llm_circuit.call(main_llm.chat,[{"role":"user","content":user_text}],system)
    answer = response.text
    cache_mgr.set_semantic(state["input_text"], answer)
    return {
        "final_answer":answer,
        "messages":[{"role":"user","content":state["input_text"]},
                    {"role":"assistant","content":answer}],
        "iterations":state.get("iterations",0)+1,
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

checkpointer = PostgresSaver.from_conn_string(os.environ["POSTGRES_URL"])
checkpointer.setup()
agent_app = builder.compile(checkpointer=checkpointer)

def run_agent(user_text: str, files: list = None, session_id: str = None) -> str:
    import uuid
    session_id = session_id or str(uuid.uuid4())
    result = agent_app.invoke(
        {"input_text":user_text,"input_files":files or [],"messages":[],"session_id":session_id},
        config={"configurable":{"thread_id":session_id}},
    )
    return result["final_answer"]
```

---

## СЕКЦИЯ 11 — A2A PROTOCOL

### a2a/agent_card.py
```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import yaml

config = yaml.safe_load(open("config.yaml"))
router = APIRouter()

def build_agent_card() -> dict:
    cfg = config["a2a"]
    return {
        "name": cfg["agent_name"],
        "description": cfg["description"],
        "url": cfg["agent_url"],
        "version": cfg["agent_version"],
        "provider": {"organization":"Custom","url":cfg["agent_url"]},
        "defaultInputModes": ["text","image","audio","video"],
        "defaultOutputModes": ["text","file","data"],
        "capabilities": {
            "streaming": cfg["capabilities"]["streaming"],
            "pushNotifications": cfg["capabilities"]["push_notifications"],
            "stateTransitionHistory": cfg["capabilities"]["state_transition_history"],
        },
        "skills": [{"id":s["id"],"name":s["name"],"description":s["description"],
                    "inputModes":s["input_modes"],"outputModes":s["output_modes"],
                    "tags":s["tags"]} for s in cfg["skills"]],
        "authentication": {"schemes":["apiKey"]} if cfg["auth"]["enabled"] else None,
    }

@router.get("/.well-known/agent.json")
async def get_agent_card():
    return JSONResponse(build_agent_card())
```

### a2a/server.py
```python
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from enum import Enum
import uuid, asyncio, json
from security.middleware import verify_auth

router = APIRouter(prefix="/a2a")

class TaskState(str, Enum):
    SUBMITTED="submitted"; WORKING="working"; COMPLETED="completed"
    FAILED="failed"; CANCELLED="cancelled"

class TaskSendRequest(BaseModel):
    id: Optional[str] = None
    message: dict
    metadata: Optional[dict] = None

_tasks: dict = {}
_queues: dict = {}

def _extract_input(message: dict) -> tuple:
    texts, files = [], []
    for part in message.get("parts",[]):
        if part.get("type")=="text": texts.append(part["text"])
        elif part.get("type")=="file": files.append({
            "path":part.get("file",{}).get("uri"),
            "mime":part.get("file",{}).get("mimeType"),
            "data_b64":part.get("file",{}).get("bytes")})
        elif part.get("type")=="data": texts.append(json.dumps(part.get("data",{})))
    return " ".join(texts), files

async def _run_task(task_id: str, text: str, files: list):
    from agent.graph import run_agent
    q = _queues[task_id]
    try:
        _tasks[task_id]["status"] = {"state":TaskState.WORKING}
        await q.put({"type":"status","status":{"state":TaskState.WORKING}})
        answer = await asyncio.get_event_loop().run_in_executor(None, run_agent, text, files, task_id)
        artifact = {"index":0,"parts":[{"type":"text","text":answer}]}
        _tasks[task_id].update({"status":{"state":TaskState.COMPLETED},"artifacts":[artifact]})
        await q.put({"type":"artifact","artifact":artifact})
        await q.put({"type":"status","status":{"state":TaskState.COMPLETED}})
    except Exception as e:
        _tasks[task_id]["status"] = {"state":TaskState.FAILED,"message":str(e)}
        await q.put({"type":"status","status":{"state":TaskState.FAILED}})
    finally:
        await q.put(None)

@router.post("/tasks/send", dependencies=[Depends(verify_auth)])
async def send_task(req: TaskSendRequest):
    task_id = req.id or str(uuid.uuid4())
    text, files = _extract_input(req.message)
    _tasks[task_id] = {"id":task_id,"status":{"state":TaskState.SUBMITTED},"artifacts":[]}
    _queues[task_id] = asyncio.Queue()
    asyncio.create_task(_run_task(task_id, text, files))
    return _tasks[task_id]

@router.get("/tasks/{task_id}", dependencies=[Depends(verify_auth)])
async def get_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404,"Task not found")
    return _tasks[task_id]

@router.post("/tasks/{task_id}/cancel", dependencies=[Depends(verify_auth)])
async def cancel_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404)
    _tasks[task_id]["status"] = {"state":TaskState.CANCELLED}
    return _tasks[task_id]

@router.get("/tasks/{task_id}/stream", dependencies=[Depends(verify_auth)])
async def stream_task(task_id: str):
    if task_id not in _queues: raise HTTPException(404)
    async def gen():
        while True:
            ev = await _queues[task_id].get()
            if ev is None: break
            yield f"data: {json.dumps(ev)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### a2a/client.py
```python
import httpx, asyncio, json, yaml, os
from dataclasses import dataclass

config  = yaml.safe_load(open("config.yaml"))
API_KEY = os.getenv(config["a2a"]["auth"].get("api_key_env","A2A_API_KEY"),"")

@dataclass
class AgentInfo:
    url: str; name: str; skills: list; input_modes: list

class A2AClient:
    def __init__(self):
        self._agents: dict = {}
        for peer in config["a2a"].get("registry",{}).get("peer_agents",[]):
            self._agents[peer["name"].lower()] = AgentInfo(
                url=peer["url"],name=peer["name"],skills=[],input_modes=["text"])

    def _headers(self):
        return {"Authorization":f"Bearer {API_KEY}"} if config["a2a"]["auth"]["enabled"] else {}

    async def discover(self, url: str) -> AgentInfo:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{url}/.well-known/agent.json", timeout=10)
            card = r.json()
        info = AgentInfo(url=url,name=card["name"],
                         skills=[s["id"] for s in card.get("skills",[])],
                         input_modes=card.get("defaultInputModes",["text"]))
        self._agents[card["name"].lower()] = info
        return info

    async def send_task(self, agent_name_or_url: str, text: str,
                        files: list = None, timeout: int = 120) -> str:
        key   = agent_name_or_url.lower()
        agent = self._agents.get(key) or await self.discover(agent_name_or_url)
        parts = [{"type":"text","text":text}]
        for f in (files or []):
            parts.append({"type":"file","file":{"name":f.get("name"),
                          "mimeType":f.get("mime"),"bytes":f.get("data_b64")}})
        async with httpx.AsyncClient(timeout=timeout, headers=self._headers()) as c:
            r   = await c.post(f"{agent.url}/a2a/tasks/send",
                               json={"message":{"role":"user","parts":parts}})
            tid = r.json()["id"]
            while True:
                await asyncio.sleep(1)
                r  = await c.get(f"{agent.url}/a2a/tasks/{tid}")
                st = r.json()["status"]["state"]
                if st == "completed":
                    arts = r.json().get("artifacts",[])
                    return arts[0]["parts"][0].get("text","") if arts else ""
                elif st in ("failed","cancelled"):
                    raise RuntimeError(f"Agent task {st}")

a2a_client = A2AClient()

DELEGATE_TOOL = {
    "name":"delegate_to_agent",
    "description":"""Delegate to a specialist agent via A2A.
Available: DataAnalyst, Translator.
Use when task is outside your knowledge base scope.""",
    "input_schema":{"type":"object","properties":{
        "agent_name":{"type":"string"},"task":{"type":"string"}},
    "required":["agent_name","task"]}
}
```

---

## СЕКЦИЯ 12 — FASTAPI MAIN + PROMETHEUS

### api/main.py
```python
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
```

---

## СЕКЦИЯ 13 — VALIDATE_CONFIG.PY

```python
import os, yaml
from pathlib import Path

config = yaml.safe_load(open("config.yaml"))

def validate_llm():
    errors = []
    for role in ["main","batch","vision"]:
        c = config["llm"].get(role,{})
        env = c.get("api_key_env","")
        if c.get("provider") not in ("ollama",) and env and not os.getenv(env):
            errors.append(f"  LLM [{role}]: {env} not set")
    if errors: raise EnvironmentError("Missing LLM API keys:\n"+"\n".join(errors))
    for role in ["main","batch","vision"]:
        c = config["llm"][role]
        print(f"  LLM [{role}]: {c['provider']}/{c['model']} OK")

def validate_embeddings():
    p = config["embeddings"]["provider"]
    c = config["embeddings"][p]
    env = c.get("api_key_env","")
    if p not in ("local","ollama") and env and not os.getenv(env):
        raise EnvironmentError(f"Embedding [{p}]: {env} not set")
    print(f"  Embeddings: {p}/{c.get('model','?')} OK")

def validate_vector_store():
    p = config["vector_store"]["provider"]
    c = config["vector_store"][p]
    if p == "qdrant":
        import httpx
        try:
            r = httpx.get(f"http://{c['host']}:{c['port']}/readyz",timeout=5)
            assert r.status_code == 200
            print(f"  VectorStore: qdrant @ {c['host']}:{c['port']} OK")
        except Exception as e:
            raise RuntimeError(f"Qdrant not reachable: {e}")
    else:
        print(f"  VectorStore: {p} configured")

def validate_databases():
    pg_url = os.getenv("POSTGRES_URL","")
    if not pg_url: raise EnvironmentError("POSTGRES_URL not set")
    import psycopg2
    try:
        conn = psycopg2.connect(pg_url); conn.close()
        print("  PostgreSQL: connected OK")
    except Exception as e:
        raise RuntimeError(f"PostgreSQL connection failed: {e}")
    redis_url = os.getenv("REDIS_URL","redis://localhost:6379/0")
    import redis as r
    try:
        r.from_url(redis_url).ping()
        print("  Redis: connected OK")
    except Exception as e:
        raise RuntimeError(f"Redis connection failed: {e}")

def validate_watch_folder():
    from utils.paths import get_watch_folder, is_windows_mount
    folder = get_watch_folder()
    print(f"  Watch folder: {folder}")
    if is_windows_mount(str(folder)):
        import warnings
        warnings.warn("Watch folder is on Windows FS (/mnt/c/...). Move to ~/data/ for better performance.")
    try:
        watches = int(open("/proc/sys/fs/inotify/max_user_watches").read())
        if watches < 524288:
            print(f"  WARNING: inotify watches={watches} < 524288")
    except Exception:
        pass

def validate_all():
    print("\n=== Validating configuration ===")
    validate_llm()
    validate_embeddings()
    validate_vector_store()
    validate_databases()
    validate_watch_folder()
    print("=== All checks passed ===\n")

if __name__ == "__main__":
    validate_all()
```

---

## СЕКЦИЯ 14 — .ENV + REQUIREMENTS.TXT

### .env.example
```bash
# LLM провайдеры
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...

# Базы данных
POSTGRES_URL=postgresql://agent:yourpassword@localhost:5432/agent_db
POSTGRES_PASSWORD=yourpassword
REDIS_URL=redis://localhost:6379/0

# A2A безопасность
A2A_API_KEY=a2a-secret-key-change-me

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=multimodal-graphrag-agent

# WSL2
WATCHDOG_POLLING=false
```

### requirements.txt
```
langchain>=0.3.0
langgraph>=0.2.0
langchain-anthropic>=0.3.0
langsmith>=0.1.0
anthropic>=0.40.0
openai>=1.40.0
google-generativeai>=0.8.0
cohere>=5.0.0
voyageai>=0.3.0
sentence-transformers>=3.0.0
qdrant-client>=1.9.0
psycopg2-binary>=2.9.0
pgvector>=0.3.0
pinecone-client>=3.0.0
chromadb>=0.5.0
celery>=5.4.0
redis>=5.0.0
kombu>=5.3.0
watchdog>=4.0.0
networkx>=3.3
graspologic>=3.3.0
pymupdf>=1.24.0
python-docx>=1.1.0
opencv-python-headless>=4.10.0
Pillow>=10.0.0
python-magic>=0.4.27
fastapi>=0.115.0
uvicorn>=0.30.0
python-multipart>=0.0.9
httpx>=0.27.0
slowapi>=0.1.9
prometheus-client>=0.20.0
pyyaml>=6.0.0
numpy>=1.26.0
```

---

## СЕКЦИЯ 15 — MAKEFILE + START.SH

### Makefile
```makefile
.PHONY: up down restart logs shell validate sync ps wsl-check

up: wsl-check
	@mkdir -p ~/data/knowledge
	docker compose up -d
	@echo "  Agent API:  http://localhost:8000"
	@echo "  Metrics:    http://localhost:9090/metrics"
	@echo "  Agent Card: http://localhost:8000/.well-known/agent.json"
	@echo "  KB Stats:   http://localhost:8000/kb/stats"

down:
	docker compose down

restart:
	docker compose restart agent celery-worker celery-beat

logs:
	docker compose logs -f --tail=100

shell:
	docker compose exec agent bash

validate:
	docker compose exec agent python validate_config.py

sync:
	docker compose exec celery-worker celery -A tasks.watcher call tasks.watcher.sync_knowledge_folder

ps:
	docker compose ps

wsl-check:
	@watches=$$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0); \
	if [ "$$watches" -lt 524288 ]; then \
	  echo "WARNING: inotify watches=$$watches — fix: sudo sysctl -w fs.inotify.max_user_watches=2097152"; fi
```

### start.sh
```bash
#!/bin/bash
set -euo pipefail

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Multimodal Temporal GraphRAG Agent v1.0            ║"
echo "║   Platform: Windows + WSL2 + Docker Desktop          ║"
echo "╚══════════════════════════════════════════════════════╝"

echo "[1/7] Checking WSL2 environment..."
WATCHES=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo 0)
if [ "$WATCHES" -lt 524288 ]; then
    sudo sysctl -w fs.inotify.max_user_watches=2097152
    sudo sysctl -w fs.inotify.max_user_instances=8192
fi

echo "[2/7] Checking data locations..."
mkdir -p ~/data/knowledge

echo "[3/7] Starting infrastructure..."
docker compose up -d postgres redis qdrant
until docker compose exec -T postgres pg_isready -U agent -d agent_db &>/dev/null; do sleep 2; done
until docker compose exec -T redis redis-cli ping &>/dev/null; do sleep 1; done
sleep 3
echo "  All services healthy"

echo "[4/7] Validating configuration..."
docker compose run --rm agent python validate_config.py

echo "[5/7] Initial knowledge base sync..."
docker compose run --rm celery-worker \
    celery -A tasks.watcher call tasks.watcher.sync_knowledge_folder

echo "[6/7] Starting Celery workers..."
docker compose up -d celery-worker celery-beat

echo "[7/7] Starting agent API..."
docker compose up -d agent

echo ""
echo "✓ System started!"
echo "  Chat API:   http://localhost:8000/chat"
echo "  Multimodal: http://localhost:8000/chat/multimodal"
echo "  A2A Tasks:  http://localhost:8000/a2a/tasks/send"
echo "  Health:     http://localhost:8000/health"
echo "  KB Stats:   http://localhost:8000/kb/stats"
```

---

## СЕКЦИЯ 16 — MEDIA PROCESSOR

### media/processor.py
```python
import base64, hashlib, subprocess
from pathlib import Path
from llm.adapter import vision_llm, batch_llm

def process_text_file(file_path: str, config: dict) -> dict:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        import fitz
        doc  = fitz.open(file_path)
        text = "\n\n".join(p.get_text() for p in doc)
    elif suffix == ".docx":
        from docx import Document
        doc  = Document(file_path)
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return {"content":text,"media_type":"text","doc_date":_extract_doc_date(text)}

def process_image_file(file_path: str, config: dict) -> dict:
    with open(file_path,"rb") as f:
        img_data = base64.standard_b64encode(f.read()).decode()
    ext_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
               ".gif":"image/gif",".webp":"image/webp"}
    mt = ext_map.get(Path(file_path).suffix.lower(),"image/jpeg")
    response = vision_llm.chat_with_vision(
        text="Describe for knowledge graph: entities, relationships, visible text, approximate date.",
        images_b64=[img_data])
    return {"content":response.text,"media_type":"image",
            "raw_image_data":img_data,"image_media_type":mt,"doc_date":None}

def process_audio_file(file_path: str, config: dict) -> dict:
    from openai import OpenAI
    oai = OpenAI()
    with open(file_path,"rb") as f:
        transcript = oai.audio.transcriptions.create(
            model="whisper-1",file=f,response_format="verbose_json",
            timestamp_granularities=["segment"])
    segments = [{"start":s.start,"end":s.end,"text":s.text}
                for s in (transcript.segments or [])]
    return {"content":transcript.text,"media_type":"audio","segments":segments,"doc_date":None}

def process_video_file(file_path: str, config: dict) -> dict:
    import cv2, os
    fps_target = config["media_processing"]["video_frames_per_minute"] / 60
    max_frames = config["media_processing"]["video_max_frames"]
    audio_path = str(Path(file_path).with_suffix("")) + "_audio.mp3"
    subprocess.run(["ffmpeg","-i",file_path,"-q:a","0","-map","a",audio_path,"-y"],capture_output=True)
    audio_result = (process_audio_file(audio_path,config)
                    if Path(audio_path).exists() else {"content":"","segments":[]})
    try: os.unlink(audio_path)
    except: pass
    cap  = cv2.VideoCapture(file_path)
    fps  = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1,int(fps/max(fps_target,0.001)))
    frames_data, frame_idx = [], 0
    while cap.isOpened() and len(frames_data) < max_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES,frame_idx)
        ret,frame = cap.read()
        if not ret: break
        _,buf = cv2.imencode(".jpg",frame)
        frames_data.append({"frame_number":frame_idx,"timestamp_ms":int(frame_idx/fps*1000),
                             "image_data":base64.standard_b64encode(buf).decode()})
        frame_idx += step
    cap.release()
    described = []
    for fr in frames_data:
        r = batch_llm.chat_with_vision("Briefly describe entities and actions.",
                                       [fr["image_data"]])
        described.append({**fr,"description":r.text})
    combined = audio_result["content"]+"\n\n"+\
               "\n".join(f"[{f['timestamp_ms']//1000}s] {f['description']}" for f in described)
    return {"content":combined,"media_type":"video",
            "segments":audio_result.get("segments",[]),"frames":described,"doc_date":None}

def process_file(file_path: str, config: dict) -> dict:
    suffix = Path(file_path).suffix.lower()
    if suffix in [".jpg",".jpeg",".png",".gif",".webp",".bmp"]:
        return process_image_file(file_path,config)
    elif suffix in [".mp3",".wav",".m4a",".ogg",".flac",".aac"]:
        return process_audio_file(file_path,config)
    elif suffix in [".mp4",".avi",".mov",".mkv",".webm",".m4v"]:
        return process_video_file(file_path,config)
    else:
        return process_text_file(file_path,config)

def _extract_doc_date(text: str):
    import re
    for p in [r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b',r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b']:
        m = re.search(p,text)
        if m: return m.group(0)
    return None

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(8192),b""): h.update(chunk)
    return h.hexdigest()
```

---

## СЕКЦИЯ 17 — UTILS + DATABASE

### utils/paths.py
```python
import os, warnings
from pathlib import Path

def is_windows_mount(path: str) -> bool:
    p = Path(path).resolve()
    return len(p.parts) >= 3 and p.parts[1] == "mnt" and len(p.parts[2]) == 1

def normalize_path(raw: str) -> str:
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        drive = raw[0].lower()
        rest  = raw[2:].replace("\\","/")
        path  = f"/mnt/{drive}{rest}"
        warnings.warn(f"Windows path mapped: {raw} → {path}\n"
                      f"Move data to ~/data/ for 10-50x better I/O.", UserWarning, stacklevel=3)
        return path
    return raw.replace("\\","/")

def get_watch_folder() -> Path:
    import yaml
    cfg = yaml.safe_load(open("config.yaml"))
    raw = cfg["knowledge_base"]["watch_folder"]
    raw = os.path.expandvars(raw)
    raw = os.path.expanduser(raw)
    path = Path(normalize_path(raw))
    path.mkdir(parents=True, exist_ok=True)
    return path
```

### database.py
```python
import psycopg2, psycopg2.extras, os
from typing import Optional

_conn = None

def get_db():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            os.environ["POSTGRES_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return DBWrapper(_conn)

class DBWrapper:
    def __init__(self, conn): self.conn = conn

    def fetch(self, sql: str, params=None) -> list:
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
            return [dict(r) for r in cur.fetchall()]

    def fetchone(self, sql: str, params=None) -> Optional[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
            r = cur.fetchone()
            return dict(r) if r else None

    def execute(self, sql: str, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or [])
        self.conn.commit()

    def execute_script(self, sql: str):
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()
```

---

## СЕКЦИЯ 18 — СТРУКТУРА ПРОЕКТА

```
multimodal-graphrag-agent/
├── .env                          # API ключи (в .gitignore!)
├── .env.example                  # Шаблон для .env
├── .gitattributes                # LF line endings
├── .dockerignore
├── config.yaml                   # Вся конфигурация
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── start.sh
├── requirements.txt
├── schema.sql
├── validate_config.py
├── database.py
│
├── agent/
│   ├── __init__.py
│   ├── graph.py                  # LangGraph StateGraph
│   └── tools.py                  # RAG + A2A инструменты
│
├── a2a/
│   ├── __init__.py
│   ├── agent_card.py
│   ├── server.py
│   └── client.py
│
├── api/
│   ├── __init__.py
│   └── main.py
│
├── cache/
│   ├── __init__.py
│   └── manager.py
│
├── embeddings/
│   ├── __init__.py
│   └── adapter.py
│
├── graph/
│   ├── __init__.py
│   ├── indexer.py
│   ├── query.py
│   ├── temporal.py
│   └── community.py
│
├── llm/
│   ├── __init__.py
│   └── adapter.py
│
├── media/
│   ├── __init__.py
│   └── processor.py
│
├── security/
│   ├── __init__.py
│   └── middleware.py
│
├── tasks/
│   ├── __init__.py
│   ├── watcher.py
│   └── watcher_wsl2.py
│
├── utils/
│   ├── __init__.py
│   └── paths.py
│
└── vector_store/
    ├── __init__.py
    └── adapter.py

═══════════════════════════════════════════════════════════
ПОРЯДОК ПЕРЕДАЧИ В CLAUDE CODE ДЛЯ РАЗРАБОТКИ:
═══════════════════════════════════════════════════════════

Шаг 1:  config.yaml + .env.example + .gitattributes + .dockerignore
Шаг 2:  docker-compose.yml + Dockerfile + requirements.txt
Шаг 3:  schema.sql
Шаг 4:  database.py + utils/paths.py + validate_config.py
Шаг 5:  llm/adapter.py + embeddings/adapter.py + vector_store/adapter.py
Шаг 6:  security/middleware.py + cache/manager.py
Шаг 7:  media/processor.py
Шаг 8:  graph/indexer.py + graph/query.py + graph/temporal.py + graph/community.py
Шаг 9:  tasks/watcher.py + tasks/watcher_wsl2.py
Шаг 10: a2a/agent_card.py + a2a/server.py + a2a/client.py
Шаг 11: agent/graph.py + agent/tools.py
Шаг 12: api/main.py
Шаг 13: Makefile + start.sh

═══════════════════════════════════════════════════════════
КАК ПЕРЕДАТЬ В CLAUDE CODE:
═══════════════════════════════════════════════════════════

1. Сохрани этот файл как AGENT_SPEC.md в папку проекта
2. В WSL2: cd ~/projects/multimodal-graphrag-agent && claude
3. Скажи Claude Code: "Прочитай AGENT_SPEC.md и реализуй шаг 1"
4. Переходи к следующему шагу после завершения каждого
5. После всех шагов: make up
```
