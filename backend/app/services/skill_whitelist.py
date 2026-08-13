"""Whitelist de skills ya auditadas por Gemini (skip HITL y re-auditoría)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


def code_fingerprint(code_str: str) -> str:
    normalized = (code_str or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_whitelisted(
    skill_id: str | None,
    code_str: str,
    db: Session | None = None,
) -> bool:
    sid = (skill_id or "").strip()
    if not sid or not (code_str or "").strip():
        return False
    digest = code_fingerprint(code_str)
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text(
                """
                SELECT 1
                FROM skill_whitelist
                WHERE skill_id = :skill_id AND code_sha256 = :digest
                LIMIT 1
                """
            ),
            {"skill_id": sid, "digest": digest},
        ).first()
        return row is not None
    except Exception:
        logger.exception("No se pudo consultar skill_whitelist")
        return False
    finally:
        if own:
            session.close()


def has_whitelisted_skill_id(skill_id: str | None, db: Session | None = None) -> bool:
    """True si esa skill_id ya pasó auditoría alguna vez (cualquier hash)."""
    sid = (skill_id or "").strip()
    if not sid:
        return False
    own = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text(
                """
                SELECT 1
                FROM skill_whitelist
                WHERE skill_id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": sid},
        ).first()
        return row is not None
    except Exception:
        logger.exception("No se pudo consultar skill_whitelist por id")
        return False
    finally:
        if own:
            session.close()


def can_auto_reuse_skill(skill: dict[str, Any], db: Session | None = None) -> bool:
    """
    Decide si se puede ejecutar sin HITL de descarga/ejecución.
    - Match exacto id+hash, o
    - Templates curadas ya conocidas por skill_id (código estable en repo).
    """
    sid = str(skill.get("id") or "").strip()
    code = str(skill.get("code") or "")
    if not sid or not code.strip():
        return False
    if is_whitelisted(sid, code, db=db):
        return True
    # Skills curadas (telemetría, etc.): si ya se auditó ese id, reusar sin re-pedir.
    if skill.get("template") and has_whitelisted_skill_id(sid, db=db):
        return True
    return False


def add_to_whitelist(
    *,
    skill_id: str,
    code_str: str,
    skill_name: str | None = None,
    source: str | None = None,
    audit: dict[str, Any] | None = None,
    db: Session | None = None,
) -> bool:
    """Registra una skill auditada como segura. Idempotente."""
    sid = (skill_id or "").strip()
    if not sid or not (code_str or "").strip():
        return False
    digest = code_fingerprint(code_str)
    audit = audit or {}
    own = db is None
    session = db or SessionLocal()
    try:
        session.execute(
            text(
                """
                INSERT INTO skill_whitelist (
                    skill_id, code_sha256, skill_name, source, risk_score, audit_reason
                )
                VALUES (
                    :skill_id, :digest, :skill_name, :source, :risk_score, :audit_reason
                )
                ON CONFLICT (skill_id, code_sha256) DO UPDATE SET
                    skill_name = EXCLUDED.skill_name,
                    source = COALESCE(EXCLUDED.source, skill_whitelist.source),
                    risk_score = EXCLUDED.risk_score,
                    audit_reason = EXCLUDED.audit_reason,
                    whitelisted_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "skill_id": sid,
                "digest": digest,
                "skill_name": (skill_name or sid)[:255],
                "source": (source or "local")[:64],
                "risk_score": int(audit.get("risk_score") or 0),
                "audit_reason": str(audit.get("reason") or "Auditoría Gemini OK")[:2000],
            },
        )
        session.commit()
        logger.info("Skill whitelisteada: id=%s sha256=%s…", sid, digest[:12])
        return True
    except Exception:
        logger.exception("No se pudo agregar skill a whitelist id=%s", sid)
        session.rollback()
        return False
    finally:
        if own:
            session.close()
