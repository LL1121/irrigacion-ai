"""Cliente compartido de Gemini (OCR, embeddings, sentinel)."""

from __future__ import annotations

from google import genai

from app.core.config import get_settings


def gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada")
    return genai.Client(api_key=settings.gemini_api_key)
