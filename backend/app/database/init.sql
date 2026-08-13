-- Extensión pgvector para embeddings
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Usuarios (login Google)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    picture TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Tokens OAuth cifrados (Google Calendar / Gmail / Drive)
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google',
    access_token_enc TEXT NOT NULL,
    refresh_token_enc TEXT,
    token_expiry TIMESTAMPTZ,
    scopes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user ON oauth_tokens (user_id);

-- Fragmentos de documentos indexados para RAG
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    scope TEXT NOT NULL DEFAULT 'irrigacion',
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'upload',
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_chunks_scope_chk CHECK (scope IN ('irrigacion', 'personal')),
    CONSTRAINT document_chunks_personal_user_chk CHECK (
        scope <> 'personal' OR user_id IS NOT NULL
    )
);

-- Historial de mensajes por sesión de chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    role VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Caché semántica de consultas y respuestas
CREATE TABLE IF NOT EXISTS semantic_cache (
    id BIGSERIAL PRIMARY KEY,
    user_query TEXT NOT NULL,
    query_embedding VECTOR(768) NOT NULL,
    ai_response TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices HNSW para búsqueda por similitud coseno
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_document_chunks_scope
    ON document_chunks (scope);

CREATE INDEX IF NOT EXISTS idx_document_chunks_user_scope
    ON document_chunks (user_id, scope);

CREATE INDEX IF NOT EXISTS idx_semantic_cache_query_embedding_hnsw
    ON semantic_cache
    USING hnsw (query_embedding vector_cosine_ops);

-- Índice B-Tree para recuperar historial por sesión
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages (session_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user
    ON chat_messages (user_id);

-- Skills auditadas por Gemini: skip HITL en próximas ejecuciones (mismo código)
CREATE TABLE IF NOT EXISTS skill_whitelist (
    id BIGSERIAL PRIMARY KEY,
    skill_id TEXT NOT NULL,
    code_sha256 TEXT NOT NULL,
    skill_name TEXT,
    source TEXT,
    risk_score INT,
    audit_reason TEXT,
    whitelisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (skill_id, code_sha256)
);

CREATE INDEX IF NOT EXISTS idx_skill_whitelist_skill_id
    ON skill_whitelist (skill_id);

-- Whitelist de tools Google por usuario (escritura ya autorizada)
CREATE TABLE IF NOT EXISTS tool_whitelist (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_id TEXT NOT NULL,
    whitelisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, tool_id)
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    done_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due
    ON scheduled_jobs (status, run_at);

-- Auditoría (triggers): ver 02_audit.sql / app/database/audit.sql
