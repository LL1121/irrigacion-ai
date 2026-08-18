"""Staging de skills: código descargado + máquina de estados de auditoría/permisos."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.skill_whitelist import code_fingerprint

logger = logging.getLogger(__name__)

STATUS_DOWNLOADED = "DOWNLOADED"
STATUS_PENDING_AUDIT = "PENDING_AUDIT"
STATUS_REQUIRES_PERMISSION = "REQUIRES_PERMISSION"
STATUS_APPROVED = "APPROVED"
STATUS_FAILED = "FAILED"

APPROVAL_KIND_NETWORK = "network_permission"

AUDIT_RETRY_PROMPT = (
    "Se descargó el código pero la API de auditoría está saturada temporalmente. "
    "Decime cuando quieras reintentar la auditoría."
)

NETWORK_CAPABILITY_LABEL = "Cliente HTTP/Socket"

_RETRY_AUDIT_RE = re.compile(
    r"(?:"
    r"prob[aá](?:\s+de\s+nuevo|\s+ahora)"
    r"|reintent[aá]r?"
    r"|ahora\s+pod[eé]s"
    r"|intent[aá]\s+(?:de\s+nuevo|ahora)"
    r"|reintentar\s+la\s+auditor"
    r")",
    re.IGNORECASE,
)


def network_permission_prompt(
    capability_label: str = NETWORK_CAPABILITY_LABEL,
) -> str:
    return (
        f"La skill requiere acceso a red (`{capability_label}`) para funcionar. "
        "¿Autorizás este permiso para ejecutarla en el Sandbox?"
    )


def is_audit_retry(message: str) -> bool:
    blob = (message or "").strip()
    if not blob:
        return False
    return bool(_RETRY_AUDIT_RE.search(blob))


def skill_from_staging(row: dict[str, Any]) -> dict[str, Any]:
    args = row.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return {
        "id": row.get("skill_id"),
        "name": row.get("skill_name") or row.get("skill_id"),
        "code": row.get("code") or "",
        "source": row.get("source") or "remote",
        "arguments": args,
        "found": True,
        "description": "",
    }


def persist_staging_file(session_id: str, skill_id: str, code: str) -> str | None:
    sid = (session_id or "").strip()
    kid = re.sub(r"[^a-zA-Z0-9._-]+", "_", (skill_id or "skill").strip()) or "skill"
    if not sid:
        return None
    try:
        dest = Path(get_settings().skill_workspace_dir) / "staging" / sid
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{kid}.py"
        path.write_text(code or "", encoding="utf-8")
        return str(path)
    except OSError:
        logger.warning("No se pudo persistir la skill en staging en disco")
        return None


def upsert_skill_staging(
    *,
    session_id: str,
    skill: dict[str, Any],
    status: str,
    user_id: str | None = None,
    needs_network: bool | None = None,
    network_granted: bool | None = None,
    last_error: str | None = None,
    audit: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any] | None:
    sid = str(session_id or "").strip()
    skill_id = str(skill.get("id") or "").strip() or "pending_skill"
    code = str(skill.get("code") or "")
    if not sid or not code.strip():
        return None
    persist_staging_file(sid, skill_id, code)
    digest = code_fingerprint(code)
    args = skill.get("arguments") if isinstance(skill.get("arguments"), dict) else {}
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text(
                """
                INSERT INTO skill_staging (
                    session_id, user_id, skill_id, skill_name, source, code,
                    code_sha256, arguments, status, needs_network, network_granted,
                    last_error, audit_json, updated_at
                )
                VALUES (
                    CAST(:session_id AS uuid),
                    CAST(:user_id AS uuid),
                    :skill_id, :skill_name, :source, :code, :digest,
                    CAST(:arguments AS jsonb), :status,
                    :needs_network, :network_granted, :last_error,
                    CAST(:audit_json AS jsonb), CURRENT_TIMESTAMP
                )
                ON CONFLICT (session_id, skill_id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, skill_staging.user_id),
                    skill_name = EXCLUDED.skill_name,
                    source = COALESCE(EXCLUDED.source, skill_staging.source),
                    code = EXCLUDED.code,
                    code_sha256 = EXCLUDED.code_sha256,
                    arguments = EXCLUDED.arguments,
                    status = EXCLUDED.status,
                    needs_network = CASE
                        WHEN :needs_network_set THEN EXCLUDED.needs_network
                        ELSE skill_staging.needs_network
                    END,
                    network_granted = CASE
                        WHEN :network_granted_set THEN EXCLUDED.network_granted
                        ELSE skill_staging.network_granted
                    END,
                    last_error = EXCLUDED.last_error,
                    audit_json = COALESCE(EXCLUDED.audit_json, skill_staging.audit_json),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING
                    id, session_id, user_id, skill_id, skill_name, source, code,
                    code_sha256, arguments, status, needs_network, network_granted,
                    last_error, audit_json
                """
            ),
            {
                "session_id": sid,
                "user_id": str(user_id) if user_id else None,
                "skill_id": skill_id[:255],
                "skill_name": str(skill.get("name") or skill_id)[:255],
                "source": str(skill.get("source") or "remote")[:64],
                "code": code,
                "digest": digest,
                "arguments": json.dumps(args, ensure_ascii=False),
                "status": status,
                "needs_network": bool(needs_network)
                if needs_network is not None
                else False,
                "needs_network_set": needs_network is not None,
                "network_granted": bool(network_granted)
                if network_granted is not None
                else False,
                "network_granted_set": network_granted is not None,
                "last_error": (last_error or None),
                "audit_json": json.dumps(audit, ensure_ascii=False)
                if audit is not None
                else None,
            },
        ).mappings().first()
        if own:
            session.commit()
        return dict(row) if row else None
    except Exception:
        logger.exception("No se pudo persistir skill_staging session=%s", sid)
        if own:
            session.rollback()
        return None
    finally:
        if own:
            session.close()


def get_retryable_staging(
    session_id: str,
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Última skill de la sesión esperando reintento de auditoría Gemini."""
    sid = str(session_id or "").strip()
    if not sid:
        return None
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text(
                """
                SELECT
                    id, session_id, user_id, skill_id, skill_name, source, code,
                    code_sha256, arguments, status, needs_network, network_granted,
                    last_error, audit_json
                FROM skill_staging
                WHERE session_id = CAST(:session_id AS uuid)
                  AND status = :status
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"session_id": sid, "status": STATUS_PENDING_AUDIT},
        ).mappings().first()
        return dict(row) if row else None
    except Exception:
        logger.exception("No se pudo leer skill_staging session=%s", sid)
        return None
    finally:
        if own:
            session.close()
