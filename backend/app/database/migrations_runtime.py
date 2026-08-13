"""Migraciones ligeras de schema en runtime (volúmenes ya inicializados)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection


def apply_schema_migrations(conn: Connection) -> None:
    """ALTER/CREATE idempotentes para installs existentes."""
    # gen_random_uuid (PG 13+ core / pgcrypto). IF NOT EXISTS igual puede
    # chocar entre workers uvicorn concurrentes → tolerar unique_violation.
    conn.execute(
        text(
            """
            DO $$ BEGIN
                CREATE EXTENSION IF NOT EXISTS "pgcrypto";
            EXCEPTION
                WHEN unique_violation THEN NULL;
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)"))

    conn.execute(
        text(
            """
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
            )
            """
        )
    )
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user ON oauth_tokens (user_id)")
    )

    conn.execute(
        text(
            "ALTER TABLE document_chunks "
            "ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'irrigacion'"
        )
    )
    conn.execute(
        text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS user_id UUID")
    )
    conn.execute(
        text(
            "ALTER TABLE document_chunks "
            "ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload'"
        )
    )
    conn.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS title TEXT"))
    # FK best-effort (puede fallar si ya existe)
    conn.execute(
        text(
            """
            DO $$ BEGIN
                ALTER TABLE document_chunks
                    ADD CONSTRAINT document_chunks_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_scope "
            "ON document_chunks (scope)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_user_scope "
            "ON document_chunks (user_id, scope)"
        )
    )

    conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_id UUID"))
    conn.execute(
        text(
            """
            DO $$ BEGIN
                ALTER TABLE chat_messages
                    ADD CONSTRAINT chat_messages_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_user "
            "ON chat_messages (user_id)"
        )
    )

    conn.execute(
        text(
            """
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
            )
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_skill_whitelist_skill_id "
            "ON skill_whitelist (skill_id)"
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tool_whitelist (
                id BIGSERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tool_id TEXT NOT NULL,
                whitelisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, tool_id)
            )
            """
        )
    )

    conn.execute(
        text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS metadata JSONB")
    )

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id UUID,
                kind TEXT NOT NULL,
                payload JSONB NOT NULL,
                run_at TIMESTAMPTZ NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                done_at TIMESTAMPTZ
            )
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due "
            "ON scheduled_jobs (status, run_at)"
        )
    )
    conn.execute(text("ALTER TABLE scheduled_jobs ALTER COLUMN user_id DROP NOT NULL"))

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS chat_thread_state (
                session_id UUID PRIMARY KEY,
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                summary_text TEXT NOT NULL DEFAULT '',
                last_message_id BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    # Prompts de un turno (alcance / HITL) no son conocimiento reutilizable.
    conn.execute(
        text(
            """
            DO $$ BEGIN
                DELETE FROM semantic_cache
                WHERE ai_response ~* 'contexto personal'
                   OR ai_response ~* 'autoriz[aá]s'
                   OR ai_response ~* 'qu[eé] quer[eé]s que anote';
            EXCEPTION
                WHEN undefined_table THEN NULL;
            END $$
            """
        )
    )
