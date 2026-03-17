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

-- ═══════════════════════════════════════════════════════
-- AGENT SETTINGS & RULES
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS agent_settings (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    system_prompt   TEXT DEFAULT '',
    personality     TEXT DEFAULT '',
    language        TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO agent_settings (system_prompt) VALUES ('') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS agent_rules (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_text   TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    enabled     BOOLEAN DEFAULT TRUE,
    priority    INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════
-- MCP TOOLS
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mcp_servers (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL UNIQUE,
    url         TEXT NOT NULL,
    api_key     TEXT,
    enabled     BOOLEAN DEFAULT TRUE,
    status      TEXT DEFAULT 'disconnected',
    last_check  TIMESTAMPTZ,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mcp_tools (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    server_id    UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    tool_name    TEXT NOT NULL,
    description  TEXT,
    input_schema JSONB DEFAULT '{}',
    enabled      BOOLEAN DEFAULT TRUE,
    UNIQUE (server_id, tool_name)
);
CREATE INDEX ON kg_chunks (media_type);
CREATE INDEX ON kg_events (event_date);
CREATE INDEX ON kg_events USING GIN (entity_ids);
