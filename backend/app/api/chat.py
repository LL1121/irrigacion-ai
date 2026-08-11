"""Endpoint de chat: caché semántico + motor LangGraph (RAG)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.agent import run_agent
from app.services.cache import check_semantic_cache

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    session_id: UUID
    reply: str
    from_cache: bool
    status: str


def _persist_chat_message(
    db: Session,
    session_id: UUID,
    role: str,
    message: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, role, message)
            VALUES (:session_id, :role, :message)
            """
        ),
        {
            "session_id": str(session_id),
            "role": role,
            "message": message,
        },
    )
    db.commit()


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    cached = check_semantic_cache(db, payload.message)
    if cached is not None:
        _persist_chat_message(db, payload.session_id, "user", payload.message)
        _persist_chat_message(db, payload.session_id, "assistant", cached)
        return ChatResponse(
            session_id=payload.session_id,
            reply=cached,
            from_cache=True,
            status="cache_hit",
        )

    try:
        reply = run_agent(db, payload.session_id, payload.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error del agente: {exc}") from exc

    return ChatResponse(
        session_id=payload.session_id,
        reply=reply,
        from_cache=False,
        status="agent",
    )


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
            SELECT role, message, created_at
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """
        ),
        {"session_id": str(session_id)},
    ).mappings().all()

    return {
        "session_id": str(session_id),
        "messages": [
            {
                "role": row["role"],
                "message": row["message"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ],
    }
