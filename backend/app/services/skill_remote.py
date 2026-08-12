"""Generación de skills remotas (simula descarga desde internet vía LLM)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.skill_http import extract_urls
from app.services.skill_marketplace import infer_arguments
from app.services.token_guard import fit_remote_context, fit_user_message

logger = logging.getLogger(__name__)

_GENERATION_PROMPT = """
Sos un ingeniero de skills para la oficina de Irrigación de Malargüe (Argentina).
Generá una skill Python segura que resuelva la tarea pedida.

Reglas estrictas:
- Exponé SOLO la función `run(input_data)` que recibe un dict y devuelve un dict JSON-serializable.
- Permitido: stdlib de Python, math, json, base64, io, datetime, re.
- Para Word (.docx) podés usar `from docx import Document` si hace falta.
- HTTP: usá ÚNICAMENTE la función global inyectada `fetch_url(url)` (ya existe en el runtime).
  Ejemplo:
    resp = fetch_url(input_data.get("url") or "https://...")
    if not resp.get("ok"):
        return {"error": resp.get("error")}
    data = resp.get("json")  # si es JSON
    text = resp.get("text")  # HTML/texto
- PROHIBIDO: importar requests/urllib/httpx/socket, subprocess, os.system, eval, exec,
  open de rutas arbitrarias, acceso a variables de entorno sensibles.
- Si la tarea es consultar una web/API (telemetría, altura de un punto, etc.), la skill
  DEBE llamar a fetch_url, parsear la respuesta y devolver el dato pedido.
- Leé URLs, códigos de punto e identificadores desde input_data (url, urls, punto, query).
- Si generás un archivo, devolvé content_base64, filename y mime en el resultado.

Respondé ÚNICAMENTE con un JSON válido (sin markdown) con esta forma:
{
  "id": "slug_corto_en_snake_case",
  "name": "Nombre legible de la skill",
  "description": "Qué hace en una oración",
  "code": "def run(input_data):\\n    ..."
}
""".strip()


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (text or "remote_skill").lower()).strip("_")
    return (cleaned[:48] or "remote_skill")


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("La respuesta del generador no es un objeto JSON.")
    return data


def _llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        temperature=0.15,
    )


def generate_remote_skill(task: str, *, rag_context: str = "") -> dict[str, Any]:
    """
    Genera una skill Python para la tarea (descarga simulada desde internet).
    Devuelve un registro compatible con pending_skill del agente.
    """
    llm = _llm()
    context_block = fit_remote_context(
        rag_context.strip() or "(sin contexto documental adicional)"
    )
    task_text = fit_user_message(task)
    urls = extract_urls(task)
    response = llm.invoke(
        [
            SystemMessage(content=_GENERATION_PROMPT),
            HumanMessage(
                content=(
                    f"Tarea del usuario:\n{task_text}\n\n"
                    f"URLs detectadas: {json.dumps(urls, ensure_ascii=False)}\n\n"
                    f"Contexto documental opcional:\n{context_block}\n\n"
                    "Generá la skill. Si hay URL o hay que consultar datos online, "
                    "usá fetch_url. Respondé solo JSON compacto."
                )
            ),
        ]
    )
    raw = (getattr(response, "content", None) or "").strip()
    if not raw:
        raise RuntimeError("El generador de skills no devolvió contenido.")

    try:
        payload = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.exception("JSON inválido del generador de skills: %s", raw[:500])
        raise RuntimeError("No se pudo interpretar la skill generada.") from exc

    code = str(payload.get("code") or "").strip()
    if "def run(" not in code:
        raise RuntimeError("La skill generada no define run(input_data).")

    skill_id = _slugify(str(payload.get("id") or task))
    if not skill_id.startswith("remote_"):
        skill_id = f"remote_{skill_id}"

    name = str(payload.get("name") or "Skill descargada").strip()
    description = str(payload.get("description") or f"Habilidad generada para: {task[:120]}").strip()
    arguments = infer_arguments(skill_id, task)
    arguments["query"] = task
    if urls:
        arguments["urls"] = urls
        arguments["url"] = urls[0]
    punto = re.search(
        r"(?:punto|estación|estacion|código|codigo|id)\s*[:#-]?\s*(\d{3,8})",
        task,
        re.I,
    )
    if punto:
        arguments["punto"] = punto.group(1)
    elif re.search(r"\b\d{4,6}\b", task):
        arguments["punto"] = re.search(r"\b(\d{4,6})\b", task).group(1)

    return {
        "found": True,
        "id": skill_id,
        "name": name,
        "description": description,
        "code": code,
        "arguments": arguments,
        "source": "remote",
        "score": 0,
    }
