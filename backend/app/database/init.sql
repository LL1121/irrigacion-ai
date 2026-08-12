-- Extensión pgvector para embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Fragmentos de documentos indexados para RAG
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Historial de mensajes por sesión de chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_semantic_cache_query_embedding_hnsw
    ON semantic_cache
    USING hnsw (query_embedding vector_cosine_ops);

-- Índice B-Tree para recuperar historial por sesión
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages (session_id, created_at ASC);

-- Auditoría (triggers): ver 02_audit.sql / app/database/audit.sql

