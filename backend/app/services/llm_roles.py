"""Router mínimo de roles LLM.

Un modelo habla con la persona; el resto hace laburo sucio (JSON / bytes).

  chat      → Groq (CHAT_MODEL) — única cara al usuario + tools
  summarize → Gemini Flash — estado estructurado del hilo
  vision / ocr / audit / embed → Gemini (ingest.py, sentinel.py; no reescribir)

Fase 2: DeepSeek puede implementar `summarize` con el mismo contrato JSON;
fallback Groq TPM → Gemini Flash para `chat`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GEMINI_PLACEHOLDERS = frozenset({"", "tu_api_key_de_gemini"})

_STATUS_VALUES = frozenset(
    {"waiting_inputs", "in_progress", "blocked", "done"}
)

_BLANK_OPEN_TASK = frozenset(
    {
        "",
        "ninguna",
        "ninguno",
        "none",
        "null",
        "n/a",
        "na",
        "-",
        "—",
        "sin tarea",
        "sin tareas",
        "no hay",
        "no aplica",
        "n/d",
        "nd",
    }
)


def sanitize_open_task(value: Any) -> str:
    """None / '' / 'Ninguna' / 'None' → sin tarea abierta."""
    task = re.sub(r"\s+", " ", str(value or "").strip())
    if not task:
        return ""
    if task.lower().strip(" .") in _BLANK_OPEN_TASK:
        return ""
    return task[:400]

SUMMARIZE_SYSTEM = (
    "Sos un extractor de estado de conversación. "
    "No charlés con el usuario. "
    "Devolvé SOLO un objeto JSON con estas claves:\n"
    '{"open_task": string, "status": '
    '"waiting_inputs"|"in_progress"|"blocked"|"done",'
    ' "missing": string[], "known": object, '
    '"facts": string[], "not_this": string}\n'
    "Reglas:\n"
    "- open_task: la última orden REAL "
    "(qué hay que hacer), no un 'qué datos?' "
    "ni un chiste. Si no hay orden activa, usá "
    '"" (string vacío). NUNCA pongas '
    '"Ninguna", "None", "null" ni placeholders.\n'
    "- status: waiting_inputs si faltan datos; "
    "in_progress si se está haciendo; "
    "blocked si falló; done si ya se cumplió "
    "y no hay pedido nuevo.\n"
    "- missing: datos concretos que faltan para ESA tarea.\n"
    "- known: datos ya dichos "
    "(url, punto, rango, destinatario, horario, etc.).\n"
    "- facts: 3 a 6 bullets cortos de lo acordado.\n"
    "- not_this: a qué NO volver "
    "(ej. catálogo de riego / caudal / lámina) "
    "si la tarea abierta no es eso. "
    "Vacío si la tarea SÍ es de riego.\n"
    "Si hay resumen previo, actualizalo con los turnos "
    "nuevos; no lo tires."
)


def gemini_configured() -> bool:
    settings = get_settings()
    key = (settings.gemini_api_key or "").strip()
    return bool(key) and key not in _GEMINI_PLACEHOLDERS and not (
        key.startswith("tu_api_key")
    )


def groq_configured() -> bool:
    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    return bool(key) and not key.startswith("gsk-your")


def chat_llm(*, tools: bool = False, temperature: float = 0.2) -> ChatOpenAI:
    """LLM principal (Groq). Cara al usuario."""
    from app.services.command_router import save_user_context, use_google
    from app.services.skill_marketplace import search_skill_marketplace

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        temperature=temperature,
    )
    if tools:
        from app.services.agent import (
            create_new_skill,
            execute_python_code,
            ingest_official_url,
        )

        return llm.bind_tools(
            [
                use_google,
                save_user_context,
                search_skill_marketplace,
                create_new_skill,
                ingest_official_url,
                execute_python_code,
            ]
        )
    return llm


def normalize_thread_summary(
    raw: dict[str, Any] | None,
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Contrato estable del resumidor (Gemini u otro)."""
    data = raw if isinstance(raw, dict) else {}
    prev = previous if isinstance(previous, dict) else {}
    open_task = sanitize_open_task(
        str(data.get("open_task") or "").strip()
        or str(prev.get("open_task") or "").strip()
    )
    status = str(data.get("status") or "").strip().lower()
    if status not in _STATUS_VALUES:
        status = str(prev.get("status") or "in_progress").strip().lower()
        if status not in _STATUS_VALUES:
            status = "waiting_inputs" if open_task else "done"
    missing = data.get("missing")
    if not isinstance(missing, list):
        prev_missing = prev.get("missing")
        missing = prev_missing if isinstance(prev_missing, list) else []
    missing = [str(x).strip() for x in missing if str(x).strip()][:12]
    known = data.get("known")
    if not isinstance(known, dict):
        prev_known = prev.get("known")
        known = prev_known if isinstance(prev_known, dict) else {}
    known = {
        str(k): str(v).strip()
        for k, v in known.items()
        if v not in (None, "", [], {})
    }
    facts = data.get("facts")
    if not isinstance(facts, list):
        prev_facts = prev.get("facts")
        facts = prev_facts if isinstance(prev_facts, list) else []
    facts = [str(x).strip() for x in facts if str(x).strip()][:6]
    not_this = str(data.get("not_this") or prev.get("not_this") or "").strip()
    return {
        "open_task": open_task[:400],
        "status": status,
        "missing": missing,
        "known": known,
        "facts": facts,
        "not_this": not_this[:400],
    }


def format_summary_text(summary: dict[str, Any] | None) -> str:
    """8–12 líneas para el prompt del principal. No prosa libre de Gemini."""
    data = normalize_thread_summary(summary)
    lines = ["ESTADO DEL HILO (obligatorio respetar):"]
    if data["open_task"]:
        lines.append(f"- Tarea abierta: {data['open_task']}")
    else:
        lines.append("- Tarea abierta: (ninguna clara)")
    lines.append(f"- Estado: {data['status']}")
    if data["missing"]:
        lines.append("- Falta: " + "; ".join(data["missing"][:8]))
    if data["known"]:
        bits = [f"{k}={v}" for k, v in list(data["known"].items())[:8]]
        lines.append("- Ya conocido: " + "; ".join(bits))
    for fact in data["facts"]:
        lines.append(f"- {fact}")
    if data["not_this"]:
        lines.append(f"- NO cambiar a: {data['not_this']}")
    lines.append(
        "- Si el usuario pregunta qué datos faltan o aporta un dato, "
        "seguí ESTA tarea. No ofrezcas el catálogo de riego ni otra skill "
        "salvo que esa sea la tarea abierta."
    )
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("El resumidor no devolvió un objeto JSON")
    return data


def summarize_thread(
    transcript: str,
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Especialista summarize (Gemini). None si no hay key o falla."""
    if not gemini_configured():
        return None
    from google.genai import types

    from app.core.gemini import gemini_client

    settings = get_settings()
    prev_blob = ""
    if previous:
        prev_blob = "\nResumen previo:\n" + json.dumps(
            previous, ensure_ascii=False
        )[:2000]
    try:
        client = gemini_client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=(transcript or "") + prev_blob,
            config=types.GenerateContentConfig(
                system_instruction=SUMMARIZE_SYSTEM,
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text:
            return None
        parsed = _extract_json_object(raw_text)
        return normalize_thread_summary(parsed, previous=previous)
    except Exception:
        logger.exception("Fallo el resumidor Gemini del hilo")
        return None
