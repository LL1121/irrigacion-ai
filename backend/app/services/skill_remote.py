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
from app.services.skill_marketplace import (
    extract_web_skill_args,
    has_actionable_remote_task,
    is_telemetria_request,
    merge_web_skill_arguments,
    resolve_effective_remote_task,
)
from app.services.token_guard import fit_remote_context, fit_user_message

logger = logging.getLogger(__name__)

TELEMETRIA_FULLDTO_URL = (
    "https://serviciosweb.cloud.irrigacion.gov.ar/services/telemetria/"
    "api/public/dato-medicions/fullDto"
)

# Skill curada: la SPA /public/telemetriaMovil no trae los valores en HTML;
# hay que pegarle al JSON público fullDto.
_TELEMETRIA_SKILL_CODE = r'''
def run(input_data):
    import re

    data = input_data if isinstance(input_data, dict) else {}
    punto = str(
        data.get("punto")
        or data.get("codigo")
        or data.get("codigo_maestro")
        or data.get("codigoMaestro")
        or ""
    ).strip()
    query = str(data.get("query") or data.get("pedido") or "")
    if not punto:
        m = re.search(
            r"(?:punto|estaci[oó]n|c[oó]digo|codigo|id)\s*[:#-]?\s*(\d{3,8})",
            query,
            re.I,
        )
        if m:
            punto = m.group(1)
        else:
            m2 = re.search(r"\b(\d{4,6})\b", query)
            if m2:
                punto = m2.group(1)
    if not punto:
        return {
            "ok": False,
            "error": "Falta el código de punto/estación (ej. 10009).",
        }

    api_url = str(
        data.get("api_url")
        or data.get("api")
        or "https://serviciosweb.cloud.irrigacion.gov.ar/services/telemetria/api/public/dato-medicions/fullDto"
    ).strip()
    page_url = str(data.get("url") or data.get("page_url") or "").strip()

    resp = fetch_url(api_url)
    if not resp.get("ok"):
        return {
            "ok": False,
            "error": resp.get("error") or "No pude consultar la API de telemetría",
            "api_url": api_url,
            "punto": punto,
            "page_url": page_url or None,
        }

    payload = resp.get("json")
    if not isinstance(payload, list):
        return {
            "ok": False,
            "error": "La API no devolvió una lista JSON esperada",
            "api_url": api_url,
            "punto": punto,
        }

    match = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        codigo = str(item.get("codigoMaestro") or item.get("codigo") or "").strip()
        if codigo == punto:
            match = item
            break
    if match is None:
        return {
            "ok": False,
            "error": f"No encontré el punto {punto} en la API pública",
            "api_url": api_url,
            "punto": punto,
            "total_registros": len(payload),
        }

    mediciones = []
    altura = None
    caudal = None
    for med in match.get("datoMedicionList") or []:
        if not isinstance(med, dict):
            continue
        sensor = str(med.get("sensor") or "")
        tipo = ((med.get("tipoSensor") or {}) if isinstance(med.get("tipoSensor"), dict) else {})
        tipo_nombre = str(tipo.get("nombre") or "")
        unidad_obj = med.get("unidadMedida") if isinstance(med.get("unidadMedida"), dict) else {}
        unidad = str((unidad_obj or {}).get("nombre") or "").strip()
        valor_raw = med.get("valor")
        try:
            valor = float(str(valor_raw).replace(",", ".")) if valor_raw is not None else None
        except (TypeError, ValueError):
            valor = valor_raw
        entry = {
            "sensor": sensor,
            "tipo": tipo_nombre,
            "valor": valor,
            "unidad": unidad,
            "habilitadaVista": med.get("habilitadaVista"),
        }
        mediciones.append(entry)
        sensor_l = sensor.lower()
        tipo_l = tipo_nombre.lower()
        if altura is None and ("altura" in sensor_l or tipo_l == "altura"):
            altura = {"valor": valor, "unidad": unidad or "cm", "sensor": sensor}
        if caudal is None and ("caudal" in sensor_l or tipo_l == "caudal"):
            caudal = {"valor": valor, "unidad": unidad or "l/s", "sensor": sensor}

    return {
        "ok": True,
        "punto": punto,
        "nombre": match.get("maestroSensor"),
        "fecha": match.get("fecha"),
        "latitud": match.get("latitud"),
        "longitud": match.get("longitud"),
        "altura": altura,
        "caudal": caudal,
        "mediciones": mediciones,
        "api_url": api_url,
        "page_url": page_url or None,
        "fuente": "API pública fullDto (no scrapear la SPA)",
    }
'''.lstrip()

_GENERATION_PROMPT = """
Sos un ingeniero de skills para la oficina de Irrigación de Malargüe (Argentina).
Generá una skill Python segura que resuelva la tarea pedida.

Reglas estrictas:
- Exponé SOLO la función `run(input_data)` que recibe un dict y devuelve un dict JSON-serializable.
- Permitido: stdlib de Python, math, json, base64, io, datetime, re.
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
- Si la tarea es consultar una web/API, la skill DEBE llamar a fetch_url, parsear y
  devolver el dato pedido. NUNCA inventes números (alturas, caudales, etc.).
- Si no podés obtener el dato, devolvé {"ok": False, "error": "..."}.
- Leé url/api_url/punto/query desde input_data. No exijas una URL de SPA si hay api_url.
- NO generes una skill metafórica de "descargar skill". La skill tiene que hacer la tarea real.
- Si generás un archivo, devolvé content_base64, filename y mime en el resultado.

Telemetría DGI (importante):
- La web /public/telemetriaMovil es una SPA: NO scrapees HTML buscando altura.
- Usá la API JSON:
  https://serviciosweb.cloud.irrigacion.gov.ar/services/telemetria/api/public/dato-medicions/fullDto
- Filtrá por codigoMaestro == punto. Altura suele estar en Sensor-*-Altura* (unidad cm).
  Caudal en Sensor-*-Caudal* (unidad l/s). Devolvé valor + unidad reales del JSON.

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


def remote_skill_rejection_reason(
    *,
    skill_id: str = "",
    name: str = "",
    description: str = "",
    code: str = "",
    task: str = "",
) -> str | None:
    """
    Gate duro anti-flash: None si la skill es usable; si no, motivo corto.
    Bloquea skills meta tipo 'Descargar Skill' que solo confirman la descarga.
    """
    blob = f"{skill_id} {name} {description}".lower()
    code_str = code or ""
    code_l = code_str.lower()
    task_l = (task or "").lower()
    has_fetch = "fetch_url" in code_l

    if "def run(" not in code_str:
        return "missing_run"

    if _META_NAME_RE.search(blob):
        if not has_fetch or _STUB_SUCCESS_RE.search(code_str):
            return "meta_download_skill"
        if re.search(
            r"return\s*\{[^}]{0,200}(?:[eé]xito|success|descarg)",
            code_str,
            re.I | re.S,
        ):
            if "punto" not in code_l and "json" not in code_l and "altura" not in code_l:
                return "meta_download_stub"

    if _STUB_SUCCESS_RE.search(code_str) and not has_fetch:
        return "stub_download_code"

    needs_http = bool(extract_urls(task)) or bool(
        re.search(
            r"http|https|www\.|web|api|telemetr|url|consult|entrar|scrap|fetch",
            task_l,
        )
    )
    if needs_http and not has_fetch:
        return "missing_fetch_url"

    if not has_fetch:
        if re.search(
            r"['\"]ok['\"]\s*:\s*True|estado.{0,20}[eé]xito|success",
            code_str,
            re.I,
        ):
            if "input_data" not in code_l or code_l.count("input_data") <= 1:
                return "noop_stub"

    return None


def validate_remote_skill(skill: dict[str, Any], task: str = "") -> None:
    """Raise RuntimeError si la skill es meta/inválida."""
    reason = remote_skill_rejection_reason(
        skill_id=str(skill.get("id") or ""),
        name=str(skill.get("name") or ""),
        description=str(skill.get("description") or ""),
        code=str(skill.get("code") or ""),
        task=task or str((skill.get("arguments") or {}).get("query") or ""),
    )
    if reason:
        raise RuntimeError(
            "Se rechazó una skill inválida "
            f"({reason}): no puede ser solo 'descargar skill'. "
            "Tiene que resolver la tarea real (consultar API/datos)."
        )


def _build_telemetria_skill(task: str) -> dict[str, Any]:
    arguments = merge_web_skill_arguments({"query": task}, task)
    arguments["api_url"] = TELEMETRIA_FULLDTO_URL
    skill = {
        "found": True,
        "id": "remote_telemetria_punto",
        "name": "Telemetría por punto (API pública)",
        "description": (
            "Consulta altura/caudal de un punto vía API fullDto de telemetría DGI "
            "(no scrapea la SPA móvil)."
        ),
        "code": _TELEMETRIA_SKILL_CODE,
        "arguments": arguments,
        "source": "remote",
        "score": 0,
        "template": "telemetria_fullDto",
    }
    validate_remote_skill(skill, task)
    return skill


def resolve_reusable_remote_skill(
    task: str,
    *,
    conversation_context: str | None = None,
) -> dict[str, Any] | None:
    """
    Si ya hay una skill remota instalada/auditada para esta tarea (p.ej. telemetría),
    devolverla lista para auto-ejecutar sin pedir descarga de nuevo.
    """
    from app.services.skill_whitelist import can_auto_reuse_skill

    effective = resolve_effective_remote_task(task, conversation_context)
    candidates: list[dict[str, Any]] = []
    if is_telemetria_request(effective) or is_telemetria_request(task or ""):
        candidates.append(_build_telemetria_skill(effective))

    for skill in candidates:
        if can_auto_reuse_skill(skill):
            # Refrescar args con el pedido actual (punto/URL pueden cambiar).
            skill["arguments"] = merge_web_skill_arguments(
                dict(skill.get("arguments") or {}),
                effective,
            )
            skill["arguments"]["query"] = effective
            logger.info(
                "Reusando skill remota whitelisteada id=%s (sin re-descarga)",
                skill.get("id"),
            )
            return skill
    return None


def _fallback_for_invalid_skill(task: str, urls: list[str]) -> dict[str, Any] | None:
    if is_telemetria_request(task) or any("irrigacion.gov.ar" in u for u in urls):
        return _build_telemetria_skill(task)
    return None


def generate_remote_skill(
    task: str,
    *,
    rag_context: str = "",
    conversation_context: str | None = None,
) -> dict[str, Any]:
    """
    Genera una skill Python para la tarea (descarga simulada desde internet).
    Devuelve un registro compatible con pending_skill del agente.
    """
    effective_task = resolve_effective_remote_task(task, conversation_context)
    urls = extract_urls(effective_task)

    if not has_actionable_remote_task(effective_task):
        raise RuntimeError(
            "No hay una tarea concreta para generar la skill "
            "(solo vi una confirmación tipo 'descargá la skill'). "
            "Pedime el dato, la URL/API y el punto si aplica."
        )

    if is_telemetria_request(effective_task) or is_telemetria_request(task or ""):
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
                    "Mensaje corto actual (puede ser confirmación; IGNORALO como objetivo):\n"
                    f"{fit_user_message(task)}\n\n"
                    f"URLs detectadas: {json.dumps(urls, ensure_ascii=False)}\n"
                    f"Args detectados: {json.dumps(web_args, ensure_ascii=False)}\n\n"
                    f"Contexto documental opcional:\n{context_block}\n\n"
                    "Generá la skill para la TAREA REAL. Si hay que consultar datos online, "
                    "usá fetch_url. No inventes números. Respondé solo JSON compacto."
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

    name = str(payload.get("name") or "Skill remota").strip()
    if _META_NAME_RE.search(name):
        name = "Consulta de datos solicitada"
    description = str(
        payload.get("description") or f"Habilidad generada para: {effective_task[:120]}"
    ).strip()

    skill_id = _slugify(str(payload.get("id") or effective_task))
    if not skill_id.startswith("remote_"):
        skill_id = f"remote_{skill_id}"
    if _META_NAME_RE.search(skill_id):
        skill_id = "remote_consulta_datos"

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

    arguments = merge_web_skill_arguments({"query": effective_task}, effective_task)
    skill = {
        "found": True,
        "id": skill_id,
        "name": name,
        "description": description,
        "code": code,
        "arguments": arguments,
        "source": "remote",
        "score": 0,
    }
    validate_remote_skill(skill, effective_task)
    return skill

