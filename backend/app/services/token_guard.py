"""Límites de tokens/contexto para no reventar cuotas de Groq/Gemini."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Heurística estable sin tiktoken: ~4 chars ≈ 1 token en español/inglés mixto.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def truncate_chars(text: str, max_chars: int, *, suffix: str = "…[truncado]") -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def truncate_to_tokens(text: str, max_tokens: int, *, suffix: str = "…[truncado]") -> str:
    if max_tokens <= 0:
        return ""
    return truncate_chars(text, max_tokens * _CHARS_PER_TOKEN, suffix=suffix)


def token_budget() -> dict[str, int]:
    """Presupuestos configurables (tokens aproximados)."""
    from app.core.config import get_settings

    settings = get_settings()
    return {
        # Tope duro por request de chat hacia Groq (dejar margen vs TPM 12k).
        "request_max": int(getattr(settings, "llm_request_max_tokens", 9000)),
        "system_max": int(getattr(settings, "llm_system_max_tokens", 1800)),
        "rag_max": int(getattr(settings, "llm_rag_max_tokens", 3500)),
        "history_max": int(getattr(settings, "llm_history_max_tokens", 1800)),
        "user_max": int(getattr(settings, "llm_user_max_tokens", 1500)),
        "skill_result_max": int(getattr(settings, "llm_skill_result_max_tokens", 1200)),
        "remote_skill_context_max": int(
            getattr(settings, "llm_remote_skill_context_max_tokens", 2500)
        ),
        "audit_code_max": int(getattr(settings, "llm_audit_code_max_tokens", 4000)),
        "history_msg_max": int(getattr(settings, "llm_history_message_max_tokens", 400)),
        "rag_doc_max": int(getattr(settings, "llm_rag_doc_max_tokens", 900)),
    }


_BINARY_KEYS = {
    "content_base64",
    "file_base64",
    "data_base64",
    "bytes_base64",
    "raw_base64",
}


def sanitize_json_for_llm(value: Any, *, depth: int = 0, max_str: int = 2000) -> Any:
    """Elimina blobs binarios y recorta strings grandes."""
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in _BINARY_KEYS or key_l.endswith("_base64"):
                size = len(str(item)) if item is not None else 0
                out[key] = f"[omitido: {size} chars base64]"
                continue
            if key_l in {"stdout", "stderr"} and isinstance(item, str):
                out[key] = truncate_chars(item, max_str)
                continue
            out[key] = sanitize_json_for_llm(item, depth=depth + 1, max_str=max_str)
        return out
    if isinstance(value, list):
        return [
            sanitize_json_for_llm(item, depth=depth + 1, max_str=max_str)
            for item in value[:40]
        ]
    if isinstance(value, str):
        return truncate_chars(value, max_str)
    return value


def dumps_capped(value: Any, *, max_tokens: int) -> str:
    sanitized = sanitize_json_for_llm(value)
    text = json.dumps(sanitized, ensure_ascii=False, indent=2)
    return truncate_to_tokens(text, max_tokens)


def fit_rag_docs(docs: list[str]) -> list[str]:
    """Recorta cada doc y el total del bloque RAG."""
    budget = token_budget()
    per_doc = budget["rag_doc_max"]
    total = budget["rag_max"]
    fitted: list[str] = []
    used = 0
    for doc in docs:
        piece = truncate_to_tokens(doc, per_doc)
        cost = estimate_tokens(piece)
        if used + cost > total:
            remaining = total - used
            if remaining < 80:
                break
            piece = truncate_to_tokens(piece, remaining)
            fitted.append(piece)
            break
        fitted.append(piece)
        used += cost
    if len(fitted) < len(docs):
        logger.info(
            "Token guard: RAG recortado de %s a %s docs (~%s tokens)",
            len(docs),
            len(fitted),
            used,
        )
    return fitted


def fit_history(history: list[dict]) -> list[dict]:
    """Recorta mensajes de historial por mensaje y por presupuesto total."""
    budget = token_budget()
    per_msg = budget["history_msg_max"]
    total = budget["history_max"]
    fitted: list[dict] = []
    used = 0
    # Priorizar mensajes recientes (historial ya viene en orden cronológico).
    for item in reversed(history):
        role = item.get("role") or ""
        message = truncate_to_tokens(str(item.get("message") or ""), per_msg)
        cost = estimate_tokens(message) + 4
        if used + cost > total:
            break
        fitted.append({"role": role, "message": message})
        used += cost
    fitted.reverse()
    if len(fitted) < len(history):
        logger.info(
            "Token guard: historial recortado de %s a %s mensajes (~%s tokens)",
            len(history),
            len(fitted),
            used,
        )
    return fitted


def fit_user_message(text: str) -> str:
    return truncate_to_tokens(text or "", token_budget()["user_max"])


def fit_system_prompt(text: str) -> str:
    return truncate_to_tokens(text or "", token_budget()["system_max"])


def fit_remote_context(text: str) -> str:
    return truncate_to_tokens(text or "", token_budget()["remote_skill_context_max"])


def fit_audit_code(code: str) -> str:
    return truncate_to_tokens(code or "", token_budget()["audit_code_max"])


def estimate_messages_tokens(parts: list[str]) -> int:
    return sum(estimate_tokens(p) for p in parts)


def enforce_request_budget(parts: list[tuple[str, str]]) -> list[str]:
    """
    Recorta dinámicamente bloques etiquetados para caber en request_max.
    parts: lista de (label, text) en orden de prioridad (los últimos se recortan primero).
    """
    budget = token_budget()["request_max"]
    texts = [t for _, t in parts]
    total = estimate_messages_tokens(texts)
    if total <= budget:
        return texts

    # Recortar desde el final hacia atrás (user/rag/history suelen ir al final).
    mutable = list(texts)
    for idx in range(len(mutable) - 1, -1, -1):
        total = estimate_messages_tokens(mutable)
        if total <= budget:
            break
        overflow = total - budget
        current = mutable[idx]
        current_tokens = estimate_tokens(current)
        keep = max(120, current_tokens - overflow - 20)
        mutable[idx] = truncate_to_tokens(current, keep)
        logger.warning(
            "Token guard: recortando bloque '%s' a ~%s tokens (overflow=%s)",
            parts[idx][0],
            keep,
            overflow,
        )
    return mutable
