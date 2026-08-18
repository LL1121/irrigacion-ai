"""Cola simple de acciones diferidas (mails programados)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STOP = threading.Event()
_WORKER: threading.Thread | None = None


def enqueue_job(
    db: Session,
    *,
    user_id: str | None,
    session_id: str | None,
    kind: str,
    payload: dict[str, Any],
    run_at: datetime,
) -> str:
    row = db.execute(
        text(
            """
            INSERT INTO scheduled_jobs (user_id, session_id, kind, payload, run_at)
            VALUES (
                CAST(:user_id AS uuid),
                :session_id,
                :kind,
                CAST(:payload AS jsonb),
                :run_at
            )
            RETURNING id::text
            """
        ),
        {
            "user_id": user_id,
            "session_id": session_id,
            "kind": kind,
            "payload": json.dumps(payload, ensure_ascii=False),
            "run_at": run_at,
        },
    ).scalar_one()
    db.commit()
    return str(row)


def _due_jobs(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id::text AS id, user_id::text AS user_id, session_id, kind, payload
            FROM scheduled_jobs
            WHERE status = 'pending' AND run_at <= CURRENT_TIMESTAMP
            ORDER BY run_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 10
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _mark_job(db: Session, job_id: str, *, status: str, error: str | None = None) -> None:
    db.execute(
        text(
            """
            UPDATE scheduled_jobs
            SET status = :status, error = :error, done_at = CURRENT_TIMESTAMP
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"status": status, "error": error, "id": job_id},
    )


def _post_chat(db: Session, job: dict[str, Any], message: str) -> None:
    session_id = job.get("session_id")
    if not session_id:
        return
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, user_id, role, message)
            VALUES (
                CAST(:session_id AS uuid),
                CAST(:user_id AS uuid),
                'assistant',
                :message
            )
            """
        ),
        {
            "session_id": session_id,
            "user_id": job.get("user_id"),
            "message": message,
        },
    )


def _run_job(db: Session, job: dict[str, Any]) -> None:
    from app.services.google_workspace import gmail_send_message
    from app.services.sandbox import execute_skill_sync

    kind = job.get("kind")
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    if kind == "gmail_send":
        gmail_send_message(
            db,
            str(job["user_id"]),
            to=str(payload.get("to") or ""),
            subject=str(payload.get("subject") or "Mensaje"),
            body=str(payload.get("body") or ""),
        )
        to = payload.get("to") or "?"
        subject = payload.get("subject") or ""
        _post_chat(
            db,
            job,
            f"Mandé el mail programado a **{to}** con asunto «{subject}».",
        )
        return
    if kind == "skill_execute":
        skill = payload.get("skill") or {}
        result = execute_skill_sync(
            str(skill.get("code") or ""),
            skill.get("arguments") or {},
            skill_id=str(skill.get("id") or "") or None,
            skill_name=str(skill.get("name") or "") or None,
            source=str(skill.get("source") or "local") or None,
            allow_network=bool(payload.get("allow_network")),
        )
        name = skill.get("name") or "la tarea"
        status = (result or {}).get("status") or "ok"
        if status == "error":
            err = ((result or {}).get("execution") or {}).get("error") or "error"
            _post_chat(db, job, f"Falló la tarea programada ({name}): {err}")
            raise RuntimeError(str(err))
        if status == "audit_unavailable":
            _post_chat(
                db,
                job,
                f"Quedó lista **{name}** pero la API de auditoría estaba saturada. "
                "Decime cuando quieras reintentar la auditoría.",
            )
            raise RuntimeError("audit_unavailable")
        if status in {"rejected", "needs_network"}:
            reason = ((result or {}).get("audit") or {}).get("reason") or status
            _post_chat(
                db,
                job,
                f"No pude ejecutar la tarea programada ({name}): {reason}",
            )
            raise RuntimeError(str(reason))
        _post_chat(
            db,
            job,
            f"Listo: ejecuté **{name}** a la hora que habías pedido.",
        )
        return
    raise ValueError(f"kind desconocido: {kind}")


def process_due_jobs(db: Session) -> int:
    jobs = _due_jobs(db)
    done = 0
    for job in jobs:
        try:
            _run_job(db, job)
            _mark_job(db, job["id"], status="done")
            db.commit()
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo job programado %s", job.get("id"))
            db.rollback()
            try:
                _mark_job(db, job["id"], status="error", error=str(exc)[:500])
                db.commit()
            except Exception:
                logger.exception("No pude marcar el job %s como error", job.get("id"))
                db.rollback()
    return done


def _worker_loop() -> None:
    from app.core.database import SessionLocal

    while not _STOP.wait(20):
        db = SessionLocal()
        try:
            process_due_jobs(db)
        except Exception:
            logger.exception("Worker de jobs programados")
            db.rollback()
        finally:
            db.close()


def start_scheduled_job_worker() -> None:
    global _WORKER
    if _WORKER and _WORKER.is_alive():
        return
    _STOP.clear()
    _WORKER = threading.Thread(
        target=_worker_loop, name="scheduled-jobs", daemon=True
    )
    _WORKER.start()
    logger.info("Worker de acciones programadas arrancado")


def stop_scheduled_job_worker() -> None:
    _STOP.set()
