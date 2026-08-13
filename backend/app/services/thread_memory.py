"""Memoria persistente del hilo: Gemini resume, Groq consume el estado."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.llm_roles import format_summary_text, summarize_thread
from app.services.token_guard import truncate_to_tokens

logger = logging.getLogger(__name__)

RECENT_TURNS_WITH_SUMMARY = 8
_SUMMARIZE_MSG_MAX_TOKENS = 220
_SUMMARIZE_TRANSCRIPT_MAX_TOKENS = 3500
_MAX_MESSAGES = 30


def empty_thread_state() -> dict[str, Any]:
    return {
        "open_task": "",
        "status": "",
        "missing": [],
        "known": {},
        "facts": [],
        "not_this": "",
        "summary_json": {},
        "summary_text": "",
        "last_message_id": None,
    }


def _row_to_state(row: dict[str, Any] | None) -> dict[str, Any]:
    state = empty_thread_state()
    if not row:
        return state
    raw = row.get("summary_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    state.update(
        {
            "open_task": str(raw.get("open_task") or ""),
            "status": str(raw.get("status") or ""),
            "missing": raw.get("missing") if isinstance(raw.get("missing"), list) else [],
            "known": raw.get("known") if isinstance(raw.get("known"), dict) else {},
            "facts": raw.get("facts") if isinstance(raw.get("facts"), list) else [],
            "not_this": str(raw.get("not_this") or ""),
            "summary_json": raw,
            "summary_text": str(row.get("summary_text") or "")
            or format_summary_text(raw),
            "last_message_id": row.get("last_message_id"),
        }
    )
    return state


def load_thread_state(db: Session, session_id: str | None) -> dict[str, Any]:
    if not session_id:
        return empty_thread_state()
    row = db.execute(
        text(
            """
            SELECT summary_json, summary_text, last_message_id
            FROM chat_thread_state
            WHERE session_id = CAST(:session_id AS uuid)
            """
        ),
        {"session_id": str(session_id)},
    ).mappings().first()
    return _row_to_state(dict(row) if row else None)


def _latest_message_id(db: Session, session_id: str) -> int | None:
    value = db.execute(
        text(
            """
            SELECT MAX(id) FROM chat_messages
            WHERE session_id = CAST(:session_id AS uuid)
            """
        ),
        {"session_id": str(session_id)},
    ).scalar()
    return int(value) if value is not None else None


def _load_messages_for_summary(db: Session, session_id: str) -> list[dict[str, str]]:
    rows = db.execute(
        text(
            """
            SELECT role, message
            FROM chat_messages
            WHERE session_id = CAST(:session_id AS uuid)
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"session_id": str(session_id), "limit": _MAX_MESSAGES},
    ).mappings().all()
    return [
        {"role": str(row["role"] or ""), "message": str(row["message"] or "")}
        for row in reversed(list(rows))
    ]


def _transcript(messages: list[dict[str, str]]) -> str:
    selected: list[str] = []
    used = 0
    budget = _SUMMARIZE_TRANSCRIPT_MAX_TOKENS
    for item in reversed(messages):
        role = (item.get("role") or "user").lower()
        body = truncate_to_tokens(
            (item.get("message") or "").strip(),
            _SUMMARIZE_MSG_MAX_TOKENS,
        )
        if not body:
            continue
        line = f"{role}: {body}"
        cost = max(1, len(line) // 4)
        if used + cost > budget:
            break
        selected.append(line)
        used += cost
    selected.reverse()
    return "\n".join(selected)


def save_thread_state(
    db: Session,
    session_id: str,
    summary: dict[str, Any],
    *,
    last_message_id: int | None,
) -> dict[str, Any]:
    summary_text = format_summary_text(summary)
    db.execute(
        text(
            """
            INSERT INTO chat_thread_state (
                session_id, summary_json, summary_text, last_message_id, updated_at
            )
            VALUES (
                CAST(:session_id AS uuid),
                CAST(:summary_json AS jsonb),
                :summary_text,
                :last_message_id,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (session_id) DO UPDATE SET
                summary_json = EXCLUDED.summary_json,
                summary_text = EXCLUDED.summary_text,
                last_message_id = EXCLUDED.last_message_id,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "session_id": str(session_id),
            "summary_json": json.dumps(summary, ensure_ascii=False),
            "summary_text": summary_text,
            "last_message_id": last_message_id,
        },
    )
    db.commit()
    return _row_to_state(
        {
            "summary_json": summary,
            "summary_text": summary_text,
            "last_message_id": last_message_id,
        }
    )


def refresh_thread_state(db: Session, session_id: str) -> dict[str, Any] | None:
    """Llama al resumidor y persiste. None si no hay nada nuevo o Gemini falla."""
    sid = str(session_id)
    current_id = _latest_message_id(db, sid)
    if current_id is None:
        return None
    previous = load_thread_state(db, sid)
    prev_id = previous.get("last_message_id")
    if prev_id is not None and int(prev_id) >= int(current_id):
        return previous
    messages = _load_messages_for_summary(db, sid)
    if not messages:
        return previous if previous.get("open_task") else None
    transcript = _transcript(messages)
    if not transcript.strip():
        return previous if previous.get("open_task") else None
    prev_json = previous.get("summary_json") or None
    if isinstance(prev_json, dict) and not prev_json.get("open_task"):
        prev_json = None
    summarized = summarize_thread(transcript, previous=prev_json)
    if not summarized:
        return None
    return save_thread_state(db, sid, summarized, last_message_id=current_id)


def schedule_refresh(session_id: str | None) -> None:
    """Fuera del hot path: no bloquea la respuesta al usuario."""
    if not session_id:
        return
    thread = threading.Thread(
        target=_refresh_safe,
        args=(str(session_id),),
        name=f"thread-memory-{str(session_id)[:8]}",
        daemon=True,
    )
    thread.start()


def _refresh_safe(session_id: str) -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        refresh_thread_state(db, session_id)
    except Exception:
        logger.exception("No pude refrescar la memoria del hilo %s", session_id)
        try:
            db.rollback()
        except Exception:
            logger.debug("rollback memoria de hilo", exc_info=True)
    finally:
        db.close()


def recent_history_for_llm(
    history: list[dict[str, Any]] | None,
    thread_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Con resumen persistido, Groq solo ve los últimos turnos."""
    items = list(history or [])
    if not items:
        return items
    has_summary = bool(
        (thread_state or {}).get("summary_text")
        or (thread_state or {}).get("open_task")
    )
    if has_summary and len(items) > RECENT_TURNS_WITH_SUMMARY:
        return items[-RECENT_TURNS_WITH_SUMMARY:]
    return items


def open_task_from_state(thread_state: dict[str, Any] | None) -> str:
    if not thread_state:
        return ""
    task = str(thread_state.get("open_task") or "").strip()
    if task:
        return task
    raw = thread_state.get("summary_json")
    if isinstance(raw, dict):
        return str(raw.get("open_task") or "").strip()
    return ""
