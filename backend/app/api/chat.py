"""Endpoint de chat: caché semántico + motor LangGraph (RAG + HITL skills)."""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.checkpointer import get_checkpointer
from app.core.database import get_db
from app.services.agent import (
    DEFAULT_SPEED_MODE,
    SPEED_MODE_TOP_K,
    STATUS_APPROVAL,
    get_pending_approval,
    run_agent,
)
from app.services.auth_session import get_optional_user
from app.services.cache import check_semantic_cache
from app.services.context_memory import looks_like_save_context_intent
from app.services.google_assistant import APPROVAL_KIND_GOOGLE_TOOL, detect_google_intent
from app.services.skill_marketplace import (
    APPROVAL_KIND_DOWNLOAD,
    download_remote_prompt,
    looks_like_skill_intent,
)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(..., min_length=1)
    speed_mode: Optional[str] = DEFAULT_SPEED_MODE  # "fast" | "balanced" | "deep"

    @field_validator("speed_mode")
    @classmethod
    def _validate_speed_mode(cls, value: str | None) -> str:
        normalized = (value or DEFAULT_SPEED_MODE).lower()
        if normalized not in SPEED_MODE_TOP_K:
            return DEFAULT_SPEED_MODE
        return normalized


class ChatResponse(BaseModel):
    session_id: UUID
    reply: str
    from_cache: bool
    status: str
    skill_name: str | None = None
    skill_description: str | None = None
    attachments: list[dict[str, Any]] | None = None
    approval_kind: str | None = None


def _pending_reply(pending: dict[str, Any]) -> tuple[str, str | None, str | None]:
    kind = pending.get("approval_kind") or pending.get("intent")
    if kind == APPROVAL_KIND_DOWNLOAD:
        return download_remote_prompt(), None, None
    if kind == APPROVAL_KIND_GOOGLE_TOOL:
        name = pending.get("skill_name") or pending.get("tool_id") or "Google"
        description = pending.get("skill_description")
        return (
            f"Acción Google pendiente: {name}. ¿Autorizás?",
            name,
            description,
        )
    name = pending.get("skill_name") or "desconocida"
    description = pending.get("skill_description")
    return (
        (
            f"No tengo esta habilidad instalada. Se encontró la skill '{name}'. "
            "¿Autorizás a Gemini a auditarla y ejecutarla en el sandbox?"
        ),
        name,
        description,
    )


def _persist_chat_message(
    db: Session,
    session_id: UUID,
    role: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, user_id, role, message, metadata)
            VALUES (
                :session_id,
                CAST(:user_id AS uuid),
                :role,
                :message,
                CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "session_id": str(session_id),
            "user_id": user_id,
            "role": role,
            "message": message,
            "metadata": json.dumps(metadata, ensure_ascii=False) if metadata else None,
        },
    )
    db.commit()


def _metadata_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = get_optional_user(request, db)
    user_id = user["id"] if user else None

    pending = get_pending_approval(db, payload.session_id)
    if pending:
        reply, name, description = _pending_reply(pending)
        return ChatResponse(
            session_id=payload.session_id,
            reply=reply,
            from_cache=False,
            status=STATUS_APPROVAL,
            skill_name=name,
            skill_description=description,
            approval_kind=pending.get("approval_kind") or pending.get("intent"),
        )

    cached = None
    skip_cache = (
        looks_like_skill_intent(payload.message)
        or looks_like_save_context_intent(payload.message)
        or detect_google_intent(payload.message) is not None
    )
    if not skip_cache:
        cached = check_semantic_cache(db, payload.message)
    if cached is not None:
        _persist_chat_message(
            db, payload.session_id, "user", payload.message, user_id=user_id
        )
        _persist_chat_message(
            db, payload.session_id, "assistant", cached, user_id=user_id
        )
        return ChatResponse(
            session_id=payload.session_id,
            reply=cached,
            from_cache=True,
            status="cache_hit",
        )

    try:
        outcome = run_agent(
            db,
            payload.session_id,
            payload.message,
            speed_mode=payload.speed_mode,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error del agente: {exc}") from exc

    return ChatResponse(
        session_id=payload.session_id,
        reply=outcome.reply,
        from_cache=False,
        status=outcome.status,
        skill_name=outcome.skill_name,
        skill_description=outcome.skill_description,
        attachments=outcome.attachments,
        approval_kind=outcome.approval_kind,
    )


class TruncateSessionRequest(BaseModel):
    from_created_at: datetime


@router.post("/sessions/{session_id}/truncate")
def truncate_session(
    session_id: UUID,
    payload: TruncateSessionRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Elimina un mensaje y todo lo posterior (para editar y reenviar)."""
    db.execute(
        text(
            """
            DELETE FROM chat_messages
            WHERE session_id = :session_id
              AND created_at >= :from_created_at
            """
        ),
        {
            "session_id": str(session_id),
            "from_created_at": payload.from_created_at,
        },
    )
    db.commit()
    return {"session_id": str(session_id), "truncated_from": payload.from_created_at.isoformat()}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Borra mensajes del chat y el estado LangGraph (HITL) de la sesión."""
    sid = str(session_id)
    result = db.execute(
        text("DELETE FROM chat_messages WHERE session_id = :session_id"),
        {"session_id": sid},
    )
    db.commit()

    try:
        get_checkpointer().delete_thread(sid)
    except Exception:
        # Fallback si delete_thread no está disponible o falla.
        try:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                db.execute(
                    text(f"DELETE FROM {table} WHERE thread_id = :thread_id"),
                    {"thread_id": sid},
                )
            db.commit()
        except Exception:
            pass

    deleted = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
    return {"session_id": sid, "deleted_messages": deleted}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), limit: int = 30) -> dict:
    rows = db.execute(
        text(
            """
            SELECT
                session_id::text AS session_id,
                MAX(created_at) AS last_at,
                (
                    SELECT message
                    FROM chat_messages cm2
                    WHERE cm2.session_id = chat_messages.session_id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) AS last_message
            FROM chat_messages
            GROUP BY session_id
            ORDER BY last_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    return {
        "sessions": [
            {
                "session_id": row["session_id"],
                "last_at": row["last_at"].isoformat() if row["last_at"] else None,
                "last_message": row["last_message"],
            }
            for row in rows
        ]
    }


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: UUID, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        text(
            """
            SELECT role, message, created_at, metadata
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """
        ),
        {"session_id": str(session_id)},
    ).mappings().all()

    messages: list[dict[str, Any]] = []
    for row in rows:
        meta = _metadata_dict(row.get("metadata"))
        item: dict[str, Any] = {
            "role": row["role"],
            "message": row["message"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        if meta.get("status"):
            item["status"] = meta["status"]
        if meta.get("skill_name"):
            item["skill_name"] = meta["skill_name"]
        if meta.get("skill_description"):
            item["skill_description"] = meta["skill_description"]
        if meta.get("attachments"):
            item["attachments"] = meta["attachments"]
        if meta.get("approval_kind"):
            item["approval_kind"] = meta["approval_kind"]
        if meta.get("kind") == "requires_approval":
            item["status"] = STATUS_APPROVAL
            item["approval_kind"] = meta.get("approval_kind") or item.get("approval_kind")
        messages.append(item)

    pending = get_pending_approval(db, session_id)
    if pending:
        already = any(m.get("status") == STATUS_APPROVAL for m in messages)
        if not already:
            reply, name, description = _pending_reply(pending)
            messages.append(
                {
                    "role": "assistant",
                    "message": reply,
                    "created_at": None,
                    "status": STATUS_APPROVAL,
                    "skill_name": name,
                    "skill_description": description,
                    "approval_kind": pending.get("approval_kind") or pending.get("intent"),
                }
            )
        # Solo la última card de aprobación queda actionable.
        last_idx = max(
            (i for i, m in enumerate(messages) if m.get("status") == STATUS_APPROVAL),
            default=None,
        )
        if last_idx is not None:
            for i, m in enumerate(messages):
                if m.get("status") == STATUS_APPROVAL and i != last_idx:
                    m["status"] = "resolved_approval"
    else:
        # Checkpoint ya no está en HITL: no reabrir cards viejas del historial.
        for m in messages:
            if m.get("status") == STATUS_APPROVAL:
                m["status"] = "resolved_approval"

    return {
        "session_id": str(session_id),
        "messages": messages,
        "pending_approval": pending,
    }
