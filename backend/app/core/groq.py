"""Cliente Groq (chat) vía SDK OpenAI-compatible."""

from __future__ import annotations

from openai import OpenAI

from app.core.config import get_settings


def groq_client() -> OpenAI:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")
    return OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
    )
