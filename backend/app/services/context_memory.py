"""Detección y persistencia de 'guardá esto como contexto' (personal / irrigación)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.ingest import ingest_text_note

_SAVE_INTENT_RE = re.compile(
    r"(?:guard(?:á|a|ar)|anot(?:á|a|ar)|salv(?:á|a|ar)|record(?:á|a|ar)|memor(?:izá|iza|izar))"
    r".{0,40}(?:como\s+)?(?:contexto|importante|dato\s+clave|nota)"
    r"|(?:esto\s+es\s+importante|anotá\s+esto|guarda\s+esto|guardá\s+esto"
    r"|quiero\s+que\s+(?:lo\s+)?recuerdes?|para\s+que\s+lo\s+recuerdes?)",
    re.I,
)

_SCOPE_PERSONAL_RE = re.compile(
    r"\b(?:personal|m[ií]o|privado|solo\s+para\s+m[ií]|de\s+uso\s+personal)\b",
    re.I,
)
_SCOPE_IRRIGACION_RE = re.compile(
    r"\b(?:irrigaci[oó]n|oficina|institucional|compartid[oa]|de\s+la\s+oficina|general)\b",
    re.I,
)

_SCOPE_ONLY_RE = re.compile(
    r"^\s*(?:es\s+)?(?:contexto\s+)?(?P<scope>personal|irrigaci[oó]n|oficina|institucional|privado|m[ií]o)"
    r"(?:\s*,?\s*por\s+favor)?\s*[.!?]?\s*$",
    re.I,
)


def looks_like_save_context_intent(text: str) -> bool:
    return bool(_SAVE_INTENT_RE.search(text or ""))


def parse_context_scope(text: str) -> str | None:
    """Devuelve 'personal' | 'irrigacion' | None."""
    lowered = (text or "").strip()
    if not lowered:
        return None
    # Respuesta corta solo-alcance
    only = _SCOPE_ONLY_RE.match(lowered)
    if only:
        raw = only.group("scope").lower()
        if raw.startswith("personal") or raw in {"privado", "mio", "mío"}:
            return "personal"
        return "irrigacion"
    has_personal = bool(_SCOPE_PERSONAL_RE.search(lowered))
    has_irrig = bool(_SCOPE_IRRIGACION_RE.search(lowered))
    if has_personal and not has_irrig:
        return "personal"
    if has_irrig and not has_personal:
        return "irrigacion"
    return None


def extract_note_body(text: str) -> str:
    """Quita la consigna de guardado y deja el contenido a indexar."""
    cleaned = (text or "").strip()
    # Cortar prefijos tipo "Guardá esto como contexto: ..."
    cleaned = re.sub(
        r"^(?:por\s+favor[, ]*)?(?:guard(?:á|a|ar)|anot(?:á|a|ar)|salv(?:á|a|ar)|record(?:á|a|ar))"
        r"[^:\n]*[:\-]\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"\s*(?:como\s+contexto\s+)?(?:personal|de\s+irrigaci[oó]n|irrigaci[oó]n)\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    return cleaned or (text or "").strip()


def ask_scope_prompt() -> str:
    return (
        "¿Esto lo guardo como **contexto personal** (solo vos) "
        "o como **contexto de irrigación** (oficina compartida)?\n\n"
        "Respondé **personal** o **irrigación**."
    )


def confirm_saved_message(scope: str, title: str | None = None) -> str:
    label = "personal" if scope == "personal" else "de irrigación"
    extra = f" («{title}»)" if title else ""
    return f"Listo: lo guardé como contexto {label}{extra}."


def save_context_note(
    db: Session,
    content: str,
    *,
    scope: str,
    user_id: str | None,
) -> dict[str, Any]:
    return ingest_text_note(
        db,
        content,
        scope=scope,
        user_id=user_id,
        title=None,
    )


# Pendiente de alcance por sesión (single-worker; mismo criterio que OAuth state).
_PENDING_NOTES: dict[str, str] = {}


def set_pending_note(session_id: str, content: str) -> None:
    _PENDING_NOTES[str(session_id)] = content.strip()


def get_pending_note(session_id: str) -> str | None:
    return _PENDING_NOTES.get(str(session_id))


def clear_pending_note(session_id: str) -> None:
    _PENDING_NOTES.pop(str(session_id), None)
