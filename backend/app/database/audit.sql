-- Auditoría append-only vía triggers (idempotente).
-- Se aplica en installs nuevas (docker-entrypoint) y en arranque vía ensure_runtime_schema.

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    schema_name TEXT NOT NULL DEFAULT current_schema(),
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    row_id TEXT,
    old_data JSONB,
    new_data JSONB,
    db_user TEXT NOT NULL DEFAULT CURRENT_USER,
    client_addr INET DEFAULT inet_client_addr(),
    application_name TEXT DEFAULT NULLIF(current_setting('application_name', true), '')
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at
    ON audit_log (occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_table_op
    ON audit_log (table_name, operation);

CREATE INDEX IF NOT EXISTS idx_audit_log_row_id
    ON audit_log (table_name, row_id);

COMMENT ON TABLE audit_log IS
    'Registro append-only de INSERT/UPDATE/DELETE sobre tablas de negocio.';

-- Impide alterar o borrar filas de auditoría (solo INSERT vía triggers).
CREATE OR REPLACE FUNCTION audit_log_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_log es append-only: no se permiten %', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;
CREATE TRIGGER trg_audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_log_reject_mutation();

-- Logger genérico: guarda old/new como JSONB sin vectores (embeddings).
CREATE OR REPLACE FUNCTION audit_row_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row_id TEXT;
    v_old JSONB;
    v_new JSONB;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD) - 'embedding' - 'query_embedding';
        v_new := NULL;
        BEGIN
            v_row_id := (to_jsonb(OLD) ->> 'id');
        EXCEPTION WHEN OTHERS THEN
            v_row_id := NULL;
        END;
        INSERT INTO audit_log (schema_name, table_name, operation, row_id, old_data, new_data)
        VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP, v_row_id, v_old, v_new);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        v_old := to_jsonb(OLD) - 'embedding' - 'query_embedding';
        v_new := to_jsonb(NEW) - 'embedding' - 'query_embedding';
        BEGIN
            v_row_id := COALESCE(to_jsonb(NEW) ->> 'id', to_jsonb(OLD) ->> 'id');
        EXCEPTION WHEN OTHERS THEN
            v_row_id := NULL;
        END;
        INSERT INTO audit_log (schema_name, table_name, operation, row_id, old_data, new_data)
        VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP, v_row_id, v_old, v_new);
        RETURN NEW;
    ELSE
        v_old := NULL;
        v_new := to_jsonb(NEW) - 'embedding' - 'query_embedding';
        BEGIN
            v_row_id := (to_jsonb(NEW) ->> 'id');
        EXCEPTION WHEN OTHERS THEN
            v_row_id := NULL;
        END;
        INSERT INTO audit_log (schema_name, table_name, operation, row_id, old_data, new_data)
        VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP, v_row_id, v_old, v_new);
        RETURN NEW;
    END IF;
END;
$$;

-- chat_messages
DROP TRIGGER IF EXISTS trg_audit_chat_messages ON chat_messages;
CREATE TRIGGER trg_audit_chat_messages
    AFTER INSERT OR UPDATE OR DELETE ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION audit_row_change();

-- document_chunks
DROP TRIGGER IF EXISTS trg_audit_document_chunks ON document_chunks;
CREATE TRIGGER trg_audit_document_chunks
    AFTER INSERT OR UPDATE OR DELETE ON document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION audit_row_change();

-- semantic_cache
DROP TRIGGER IF EXISTS trg_audit_semantic_cache ON semantic_cache;
CREATE TRIGGER trg_audit_semantic_cache
    AFTER INSERT OR UPDATE OR DELETE ON semantic_cache
    FOR EACH ROW
    EXECUTE FUNCTION audit_row_change();
