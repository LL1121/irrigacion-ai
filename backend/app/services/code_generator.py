"""Generador especializado de skills Python para el Sandbox de Irrigación.

Pipeline: tarea → LLM especializado en código → skill validada.
Usa CODE_MODEL_API_KEY/CODE_MODEL_BASE_URL si están configurados;
cae a Groq si no.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.skill_http import extract_urls
from app.services.skill_marketplace import (
    extract_web_skill_args,
    has_actionable_remote_task,
    is_telemetria_request,
    merge_web_skill_arguments,
    resolve_effective_remote_task,
)
from app.services.token_guard import fit_remote_context, fit_user_message

logger = logging.getLogger(__name__)

_GENERATION_PROMPT = """
Sos un ingeniero senior de skills para la oficina de Irrigación de Malargüe (Argentina).
Generá una skill Python robusta, tipada y con manejo de errores explícito.

Reglas estrictas:
- Exponé SOLO la función `run(input_data: dict) -> dict` que devuelve un dict JSON-serializable.
- Usá type hints en los parámetros internos y en el retorno siempre que sea posible.
- Incluí docstring con descripción, parámetros y retorno.
- Manejá excepciones específicas (no bare except); devolvé {"ok": False, "error": "..."} ante fallos.
- Permitido: stdlib de Python, math, json, base64, io, datetime, re, typing.
- Para Word (.docx) podés usar `from docx import Document` si hace falta.
- HTTP: usá ÚNICAMENTE la función global inyectada `fetch_url(url)` (ya existe en el runtime).
  Ejemplo:
    resp = fetch_url(input_data.get("api_url") or input_data.get("url") or "https://...")
    if not resp.get("ok"):
        return {"ok": False, "error": resp.get("error")}
    data = resp.get("json")  # si es JSON
    text = resp.get("text")  # HTML/texto
- PROHIBIDO: importar requests/urllib/httpx/socket, subprocess, os.system, eval, exec,
  open de rutas arbitrarias, acceso a variables de entorno sensibles.
- Si la tarea consulta una web/API, la skill DEBE llamar a fetch_url, parsear y devolver
  el dato pedido. NUNCA inventes números (alturas, caudales, etc.).
- Si no podés obtener el dato, devolvé {"ok": False, "error": "..."}.
- Leé url/api_url/punto/query desde input_data. No exijas URL de SPA si hay api_url.
- NO generes una skill metafórica de "descargar skill". La skill tiene que hacer la tarea real.
- Si generás un archivo, devolvé content_base64, filename y mime en el resultado.

Telemetría DGI (importante):
- La web /public/telemetriaMovil es una SPA: NO scrapees HTML buscando altura.
- Usá la API JSON:
  https://serviciosweb.cloud.irrigacion.gov.ar/services/telemetria/api/public/dato-medicions/fullDto
- Filtrá por codigoMaestro == punto. Altura suele estar en Sensor-*-Altura* (unidad cm).
  Caudal en Sensor-*-Caudal* (unidad l/s). Devolvé valor + unidad reales del JSON.

Respondé ÚNICAMENTE con un JSON válido (sin markdown) con esta forma exacta:
{
  "id": "slug_corto_en_snake_case",
  "name": "Nombre legible de la skill",
  "description": "Qué hace en una oración",
  "required_permissions": ["network"],
  "code": "def run(input_data: dict) -> dict:\\n    ..."
}

El campo "required_permissions" es una lista de strings. Valores posibles:
- "network"    → si la skill usa fetch_url o cualquier I/O de red
- "filesystem" → si la skill escribe/lee archivos fuera de /tmp (raro en este sandbox)
Si no necesita ninguno, devolvé una lista vacía: [].
""".strip()


def _slugify(text: str) -> str:
    cleaned = re.sub(
        r"[^a-z0-9]+", "_", (text or "remote_skill").lower()
    ).strip("_")
    return cleaned[:48] or "remote_skill"


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
    """Usa CODE_MODEL si está configurado; cae a Groq si no."""
    settings = get_settings()
    code_key = (settings.code_model_api_key or "").strip()
    code_url = (settings.code_model_base_url or "").strip()
    if code_key:
        return ChatOpenAI(
            model=settings.chat_model,
            api_key=code_key,
            base_url=code_url or settings.groq_base_url,
            temperature=0.1,
        )
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        temperature=0.15,
    )


_META_NAME_RE = re.compile(
    r"(?:descarg\w*|download|instal\w*|gener\w*)\s*(?:de\s+)?(?:la\s+)?skill"
    r"|skill\s*(?:descarg\w*|download|instal\w*)"
    r"|descargar_skill|download_skill|remote_descarg",
    re.I,
)

_STUB_SUCCESS_RE = re.compile(
    r"skill\s+descargada|descargada\s+con\s+[eé]xito|download(?:ed)?\s+success"
    r"|operaci[oó]n\s+se\s+ha\s+completado|habilidad\s+descargada",
    re.I,
)

_VALID_PERMISSIONS: frozenset[str] = frozenset({"network", "filesystem"})


def generate_remote_skill(
    task: str,
    *,
    rag_context: str = "",
    conversation_context: str | None = None,
) -> dict[str, Any]:
    """Genera una skill Python tipada para la tarea.

    Args:
        task: Descripción de la tarea o mensaje del usuario.
        rag_context: Fragmentos de documentos RAG relevantes (opcional).
        conversation_context: Historial de conversación para extraer la tarea real.

    Returns:
        Dict compatible con pending_skill del agente, con required_permissions.

    Raises:
        RuntimeError: Si no se puede generar una skill válida.
    """
    # Importación diferida para evitar ciclo con skill_remote.
    from app.services.skill_remote import (
        _build_telemetria_skill,
        _fallback_for_invalid_skill,
        remote_skill_rejection_reason,
        validate_remote_skill,
    )

    effective_task = resolve_effective_remote_task(task, conversation_context)
    urls = extract_urls(effective_task)

    if not has_actionable_remote_task(effective_task):
        raise RuntimeError(
            "No hay una tarea concreta para generar la skill "
            "(solo vi una confirmación tipo 'descargá la skill'). "
            "Pedime el dato, la URL/API y el punto si aplica."
        )

    if is_telemetria_request(effective_task) or is_telemetria_request(
        task or ""
    ):
        return _build_telemetria_skill(effective_task)

    llm = _llm()
    context_block = fit_remote_context(
        rag_context.strip() or "(sin contexto documental adicional)"
    )
    task_text = fit_user_message(effective_task)
    web_args = extract_web_skill_args(effective_task)
    response = llm.invoke(
        [
            SystemMessage(content=_GENERATION_PROMPT),
            HumanMessage(
                content=(
                    "Tarea REAL a resolver (NUNCA generes una skill llamada "
                    "'Descargar Skill' ni que solo confirme una descarga):\n"
                    f"{task_text}\n\n"
                    "Mensaje corto actual (puede ser confirmación; "
                    f"IGNORALO como objetivo):\n{fit_user_message(task)}\n\n"
                    f"URLs detectadas: "
                    f"{json.dumps(urls, ensure_ascii=False)}\n"
                    f"Args detectados: "
                    f"{json.dumps(web_args, ensure_ascii=False)}\n\n"
                    f"Contexto documental opcional:\n{context_block}\n\n"
                    "Generá la skill para la TAREA REAL. "
                    "Si hay que consultar datos online, usá fetch_url. "
                    "No inventes números. Respondé solo JSON compacto "
                    "con el campo required_permissions incluido."
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
        logger.exception(
            "JSON inválido del generador de skills: %s", raw[:500]
        )
        raise RuntimeError(
            "No se pudo interpretar la skill generada."
        ) from exc

    code = str(payload.get("code") or "").strip()
    if "def run(" not in code:
        raise RuntimeError("La skill generada no define run(input_data).")

    name = str(payload.get("name") or "Skill remota").strip()
    if _META_NAME_RE.search(name):
        name = "Consulta de datos solicitada"
    description = str(
        payload.get("description")
        or f"Habilidad generada para: {effective_task[:120]}"
    ).strip()

    skill_id = _slugify(str(payload.get("id") or effective_task))
    if not skill_id.startswith("remote_"):
        skill_id = f"remote_{skill_id}"
    if _META_NAME_RE.search(skill_id):
        skill_id = "remote_consulta_datos"

    # Extraer y validar required_permissions del payload del LLM.
    raw_perms = payload.get("required_permissions")
    if isinstance(raw_perms, list):
        required_permissions = [
            p for p in raw_perms if p in _VALID_PERMISSIONS
        ]
    else:
        # Si el LLM omitió el campo, inferir desde el código.
        required_permissions = []
        if "fetch_url" in code:
            required_permissions.append("network")

    reject = remote_skill_rejection_reason(
        skill_id=skill_id,
        name=name,
        description=description,
        code=code,
        task=effective_task,
    )
    if reject:
        logger.warning("Skill remota rechazada (%s): %s", reject, name)
        fallback = _fallback_for_invalid_skill(effective_task, urls)
        if fallback:
            return fallback
        raise RuntimeError(
            "El generador armó una skill inválida "
            f"({reject}). No acepto skills que solo digan 'descargada'. "
            "Reformulá el pedido con la URL y el dato que necesitás."
        )

    arguments = merge_web_skill_arguments(
        {"query": effective_task}, effective_task
    )
    skill: dict[str, Any] = {
        "found": True,
        "id": skill_id,
        "name": name,
        "description": description,
        "required_permissions": required_permissions,
        "code": code,
        "arguments": arguments,
        "source": "remote",
        "score": 0,
    }
    validate_remote_skill(skill, effective_task)
    return skill
