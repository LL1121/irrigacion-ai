"""
Normalización de respuestas del agente → lenguaje humano.

Metodología (aplicar siempre antes de mostrar/persistir):
1. Clasificar el payload (telemetría, caudal, conversión, prorrateo, lámina,
   tiempo, archivo, error, genérico).
2. Renderizar con plantilla en español rioplatense, directa, sin JSON.
3. Si hay narración LLM, validar que no sea basura técnica; si lo es, usar (2).
4. Post-filtro de texto: si la respuesta final parece dump crudo, reescribir.

Regla de producto: el usuario ve el dato masticado, nunca el JSON interno.
"""

from __future__ import annotations

import json
import re
from typing import Any


def unwrap_result(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    inner = payload.get("result")
    if isinstance(inner, dict):
        return inner
    return payload


def looks_raw_technical(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    if raw.startswith("{") or raw.startswith("["):
        return True
    markers = (
        "Ejecuté '",
        "Resultado:\n{",
        '"api_url"',
        '"mediciones"',
        '"content_base64"',
        '"success": true',
        '"success":true',
        "Resultado del sandbox",
        "def run(",
    )
    lowered = raw.lower()
    if any(m.lower() in lowered for m in markers):
        return True
    # Muchas claves JSON seguidas = dump.
    if raw.count('":') >= 4 and raw.count("{") >= 1:
        return True
    return False


def _fmt_num(value: Any, digits: int = 3) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    formatted = f"{num:.{digits}f}".rstrip("0").rstrip(".")
    return formatted


def _friendly_fecha(fecha: Any) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", str(fecha or ""))
    if not m:
        return str(fecha)
    y, mo, d, h, mi = m.groups()
    return f"{d}/{mo}/{y} {h}:{mi}"


def classify_skill_payload(data: dict[str, Any]) -> str:
    if data.get("ok") is False or data.get("error"):
        return "error"
    if data.get("content_base64") or data.get("files") or data.get("filename"):
        return "archivo"
    if isinstance(data.get("altura"), dict) or isinstance(data.get("caudal"), dict):
        if data.get("punto") or data.get("mediciones") is not None:
            return "telemetria"
    if "lamina_mm" in data:
        return "lamina"
    if "tiempo_h" in data or "tiempo_hm" in data or "tiempo_s" in data:
        return "tiempo"
    if "asignaciones" in data and isinstance(data.get("asignaciones"), list):
        return "prorrateo"
    if "entrada" in data and ("l_s" in data or "m3_s" in data):
        return "conversion"
    if "caudal_ls" in data or "caudal_m3s" in data:
        if "area_m2" in data or "velocidad_ms" in data or "formula" in data:
            return "caudal"
        if "volumen_m3" in data:
            return "tiempo"
        return "caudal"
    return "generico"


def _humanize_error(data: dict[str, Any]) -> str:
    err = data.get("error") or data.get("mensaje") or "no se pudo obtener el dato"
    punto = data.get("punto")
    if punto:
        return f"No pude sacar el dato del punto {punto}: {err}."
    return f"No pude completar la consulta: {err}."


def _humanize_telemetria(data: dict[str, Any], user_message: str) -> str:
    altura = data.get("altura") if isinstance(data.get("altura"), dict) else None
    caudal = data.get("caudal") if isinstance(data.get("caudal"), dict) else None
    punto = data.get("punto") or data.get("codigo") or data.get("codigoMaestro")
    nombre = data.get("nombre") or data.get("maestroSensor")
    fecha = data.get("fecha")

    if punto and nombre:
        clean_name = re.sub(
            rf"^{re.escape(str(punto))}\s*[-–:]\s*",
            "",
            str(nombre),
        ).strip()
        lugar = f"punto {punto}" + (f" ({clean_name})" if clean_name else "")
    elif punto:
        lugar = f"punto {punto}"
    else:
        lugar = "punto pedido"

    asked = (user_message or "").lower()
    wants_altura = any(k in asked for k in ("altura", "nivel", "cuánta", "cuanta"))
    wants_caudal = "caudal" in asked
    if not wants_altura and not wants_caudal:
        wants_altura = bool(altura)
        wants_caudal = bool(caudal)

    bits: list[str] = []
    if wants_altura and altura and altura.get("valor") is not None:
        unidad = str(altura.get("unidad") or "cm").strip()
        bits.append(f"altura **{_fmt_num(altura['valor'])} {unidad}**")
    if wants_caudal and caudal and caudal.get("valor") is not None:
        unidad = str(caudal.get("unidad") or "l/s").strip()
        bits.append(f"caudal **{_fmt_num(caudal['valor'])} {unidad}**")
    if not bits:
        if altura and altura.get("valor") is not None:
            bits.append(
                f"altura **{_fmt_num(altura['valor'])} {altura.get('unidad') or 'cm'}**"
            )
        if caudal and caudal.get("valor") is not None:
            bits.append(
                f"caudal **{_fmt_num(caudal['valor'])} {caudal.get('unidad') or 'l/s'}**"
            )
    if not bits:
        return f"Consulté el {lugar}, pero no trajo altura/caudal legibles."

    joined = " y ".join(bits) if len(bits) == 2 else bits[0]
    when = f" (medición {_friendly_fecha(fecha)})" if fecha else ""
    return f"En el {lugar}: {joined}{when}."


def _humanize_caudal(data: dict[str, Any]) -> str:
    ls = data.get("caudal_ls")
    m3s = data.get("caudal_m3s")
    area = data.get("area_m2")
    vel = data.get("velocidad_ms")
    parts = []
    if ls is not None:
        parts.append(f"**{_fmt_num(ls)} L/s**")
    if m3s is not None:
        parts.append(f"**{_fmt_num(m3s, 6)} m³/s**")
    if not parts:
        return "Calculé el caudal, pero no vino un valor claro."
    base = f"El caudal da {' / '.join(parts)}"
    if area is not None and vel is not None:
        base += (
            f" (con área {_fmt_num(area)} m² y velocidad {_fmt_num(vel, 4)} m/s)"
        )
    return base + "."


def _humanize_conversion(data: dict[str, Any]) -> str:
    entrada = data.get("entrada") if isinstance(data.get("entrada"), dict) else {}
    valor = entrada.get("valor")
    unidad = entrada.get("unidad") or ""
    lines = [
        f"Convertí **{_fmt_num(valor)} {unidad}** a:",
        f"- **{_fmt_num(data.get('l_s'), 4)} L/s**",
        f"- **{_fmt_num(data.get('m3_s'), 6)} m³/s**",
        f"- **{_fmt_num(data.get('m3_h'), 4)} m³/h**",
        f"- **{_fmt_num(data.get('m3_dia'), 2)} m³/día**",
    ]
    return "\n".join(lines)


def _humanize_prorrateo(data: dict[str, Any]) -> str:
    total = data.get("total")
    asignaciones = data.get("asignaciones") or []
    lines = [f"Prorrateo del total **{_fmt_num(total)}**:"]
    for item in asignaciones:
        if not isinstance(item, dict):
            continue
        nombre = item.get("nombre") or "parte"
        asignado = item.get("asignado")
        peso = item.get("peso")
        prop = item.get("proporcion")
        extra = []
        if peso is not None:
            extra.append(f"peso {_fmt_num(peso)}")
        if prop is not None:
            try:
                extra.append(f"{float(prop) * 100:.1f}%")
            except (TypeError, ValueError):
                pass
        suffix = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"- **{nombre}**: {_fmt_num(asignado)}{suffix}")
    if len(lines) == 1:
        return f"Prorrateé el total {_fmt_num(total)}, pero no vinieron las partes."
    return "\n".join(lines)


def _humanize_lamina(data: dict[str, Any]) -> str:
    lamina = data.get("lamina_mm")
    vol = data.get("volumen_m3")
    ha = data.get("superficie_ha")
    m2 = data.get("superficie_m2")
    msg = f"La lámina de riego da **{_fmt_num(lamina)} mm**"
    detalles = []
    if vol is not None:
        detalles.append(f"volumen {_fmt_num(vol)} m³")
    if ha is not None:
        detalles.append(f"superficie {_fmt_num(ha, 4)} ha")
    elif m2 is not None:
        detalles.append(f"superficie {_fmt_num(m2)} m²")
    if detalles:
        msg += f" (con {', '.join(detalles)})"
    return msg + "."


def _humanize_tiempo(data: dict[str, Any]) -> str:
    hm = data.get("tiempo_hm") if isinstance(data.get("tiempo_hm"), dict) else None
    horas = data.get("tiempo_h")
    vol = data.get("volumen_m3")
    ls = data.get("caudal_ls")
    if hm and (hm.get("horas") is not None or hm.get("minutos") is not None):
        h = int(hm.get("horas") or 0)
        m = int(hm.get("minutos") or 0)
        tiempo = f"**{h} h {m} min**"
    elif horas is not None:
        tiempo = f"**{_fmt_num(horas, 4)} h**"
    else:
        seg = data.get("tiempo_s")
        tiempo = f"**{_fmt_num(seg)} s**" if seg is not None else "**sin tiempo**"
    msg = f"El tiempo de riego estimado es {tiempo}"
    detalles = []
    if vol is not None:
        detalles.append(f"volumen {_fmt_num(vol)} m³")
    if ls is not None:
        detalles.append(f"caudal {_fmt_num(ls)} L/s")
    if detalles:
        msg += f" (con {', '.join(detalles)})"
    return msg + "."


def _humanize_archivo(data: dict[str, Any], attachments: list[dict[str, Any]] | None) -> str:
    names = []
    if attachments:
        names = [str(a.get("filename") or "archivo") for a in attachments]
    elif data.get("filename"):
        names = [str(data.get("filename"))]
    title = str(data.get("titulo") or data.get("title") or "").strip()
    if names:
        joined = ", ".join(f"**{n}**" for n in names)
        if title:
            return f"Listo: armé el documento «{title}»: {joined}. Lo abrís abajo."
        return f"Listo: armé el archivo {joined}. Lo abrís abajo."
    if title:
        return f"Listo: generé el documento «{title}»."
    return "Listo: generé el archivo pedido."


def _humanize_generic(data: dict[str, Any]) -> str | None:
    skip = {
        "api_url",
        "page_url",
        "fuente",
        "mediciones",
        "code",
        "query",
        "pedido",
        "ok",
        "success",
        "status",
        "formula",
        "latitud",
        "longitud",
        "bytes",
        "content_type",
    }
    lines: list[str] = []
    for key, value in data.items():
        if key in skip or value in (None, "", {}, []):
            continue
        if isinstance(value, dict):
            # Nested simple metrics: {valor, unidad}
            if value.get("valor") is not None:
                unidad = value.get("unidad") or ""
                label = key.replace("_", " ")
                lines.append(f"- **{label}**: {_fmt_num(value['valor'])} {unidad}".rstrip())
            continue
        if isinstance(value, list):
            continue
        label = key.replace("_", " ")
        lines.append(f"- **{label}**: {value}")
        if len(lines) >= 8:
            break
    if not lines:
        return None
    return "Listo, esto es lo que salió:\n" + "\n".join(lines)


def humanize_skill_payload(
    *,
    user_message: str,
    skill_name: str = "",
    skill_data: dict[str, Any] | None = None,
    sanitized_payload: Any = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str | None:
    """Convierte el resultado de una skill a texto humano. None si no hay data."""
    data = skill_data if isinstance(skill_data, dict) else None
    if data is None:
        data = unwrap_result(sanitized_payload)
    if not isinstance(data, dict):
        return None

    kind = classify_skill_payload(data)
    if kind == "error":
        return _humanize_error(data)
    if kind == "archivo":
        return _humanize_archivo(data, attachments)
    if kind == "telemetria":
        return _humanize_telemetria(data, user_message)
    if kind == "caudal":
        return _humanize_caudal(data)
    if kind == "conversion":
        return _humanize_conversion(data)
    if kind == "prorrateo":
        return _humanize_prorrateo(data)
    if kind == "lamina":
        return _humanize_lamina(data)
    if kind == "tiempo":
        return _humanize_tiempo(data)
    return _humanize_generic(data)


def fallback_skill_reply(
    *,
    name: str,
    user_message: str,
    skill_data: dict[str, Any] | None,
    sanitized_payload: Any,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    human = humanize_skill_payload(
        user_message=user_message,
        skill_name=name,
        skill_data=skill_data,
        sanitized_payload=sanitized_payload,
        attachments=attachments,
    )
    if human:
        return human
    if attachments:
        names = ", ".join(str(a.get("filename") or "archivo") for a in attachments)
        return f"Listo: armé el archivo **{names}**. Lo abrís abajo."
    return (
        f"Listo: corrí la consulta"
        + (f" ({name})" if name else "")
        + ", pero no pude armar un resumen claro. "
        "Pedime un dato puntual y te lo digo en criollo."
    )


def llm_skill_narration_prompt(style: str) -> str:
    return (
        "Sos un colega de la oficina de Irrigación de Malargüe. "
        "Traducí el resultado a lenguaje humano, directo y breve (2-5 líneas). "
        "Reglas:\n"
        "- Nada de JSON, código, nombres de skills, api_url, sensores técnicos "
        "ni coordenadas salvo que el usuario las pida.\n"
        "- Contestá la pregunta con el dato masticado "
        "(ej. 'la altura en el punto 10009 es 4.08 cm').\n"
        "- Si hay nombre de estación o partes del prorrateo, mencionálos en criollo.\n"
        "- No inventes valores: usá solo los del JSON.\n"
        "- Unidades exactas del resultado (cm, l/s, m³, mm, etc.).\n"
        "- Si hay error, explicá simple qué falló.\n"
        f"Estilo: {style}"
    )


def normalize_assistant_reply(
    reply: str,
    *,
    user_message: str = "",
    skill_name: str = "",
    skill_data: dict[str, Any] | None = None,
    sanitized_payload: Any = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    """
    Post-filtro universal: si la respuesta final parece cruda/técnica,
    reemplazarla por la versión humanizada del payload (si hay) o un aviso corto.
    """
    text = (reply or "").strip()
    if text and not looks_raw_technical(text):
        return text

    human = humanize_skill_payload(
        user_message=user_message,
        skill_name=skill_name,
        skill_data=skill_data,
        sanitized_payload=sanitized_payload,
        attachments=attachments,
    )
    if human:
        return human

    # Intentar parsear JSON embebido en la respuesta.
    if text.startswith("{") or '"result"' in text:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
                human = humanize_skill_payload(
                    user_message=user_message,
                    skill_name=skill_name,
                    sanitized_payload=parsed,
                    attachments=attachments,
                )
                if human:
                    return human
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if text and not looks_raw_technical(text):
        return text
    if attachments:
        return fallback_skill_reply(
            name=skill_name,
            user_message=user_message,
            skill_data=skill_data,
            sanitized_payload=sanitized_payload,
            attachments=attachments,
        )
    if not text:
        return (
            "No pude armar una respuesta clara con esos datos. "
            "Reformulá la pregunta o pedime el dato puntual."
        )
    # Último recurso: no devolver JSON; mensaje honesto.
    return (
        "Tengo el resultado, pero me salió en formato técnico. "
        "Pedime de nuevo el dato (altura, caudal, lámina, etc.) y te lo digo claro."
    )
