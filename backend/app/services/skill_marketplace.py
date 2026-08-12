"""Catálogo local de skills y tool de búsqueda para el agente."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import tool

SkillRecord = dict[str, Any]

_SKILL_CAUDAL = '''
def run(input_data):
    """Q = A * v. Área en m², velocidad en m/s → caudal en m³/s y L/s."""
    area_m2 = float(input_data.get("area_m2") or input_data.get("area") or 0)
    velocidad_ms = float(
        input_data.get("velocidad_ms")
        or input_data.get("velocidad")
        or input_data.get("v")
        or 0
    )
    caudal_m3s = area_m2 * velocidad_ms
    return {
        "area_m2": area_m2,
        "velocidad_ms": velocidad_ms,
        "caudal_m3s": round(caudal_m3s, 6),
        "caudal_ls": round(caudal_m3s * 1000, 3),
        "formula": "Q = A * v",
    }
'''

_SKILL_CONVERSION = '''
def run(input_data):
    """Convierte caudales entre L/s, m³/s, m³/h y m³/día."""
    value = float(input_data.get("valor") or input_data.get("value") or 0)
    unidad = str(
        input_data.get("unidad")
        or input_data.get("from")
        or input_data.get("de")
        or "l/s"
    ).lower().replace(" ", "")
    to_m3s = {
        "l/s": 0.001,
        "ls": 0.001,
        "lps": 0.001,
        "m3/s": 1.0,
        "m3s": 1.0,
        "m3/h": 1.0 / 3600.0,
        "m3h": 1.0 / 3600.0,
        "m3/d": 1.0 / 86400.0,
        "m3/dia": 1.0 / 86400.0,
        "m3d": 1.0 / 86400.0,
    }
    factor = to_m3s.get(unidad)
    if factor is None:
        return {"error": f"Unidad no soportada: {unidad}", "soportadas": list(to_m3s)}
    m3s = value * factor
    return {
        "entrada": {"valor": value, "unidad": unidad},
        "m3_s": round(m3s, 8),
        "l_s": round(m3s * 1000, 6),
        "m3_h": round(m3s * 3600, 6),
        "m3_dia": round(m3s * 86400, 4),
    }
'''

_SKILL_PRORRATEO = '''
def run(input_data):
    """Prorratea un caudal o volumen entre derechos (acciones / hectáreas)."""
    total = float(input_data.get("total") or input_data.get("caudal_total") or 0)
    partes = input_data.get("partes") or input_data.get("derechos") or []
    if isinstance(partes, dict):
        partes = [{"nombre": k, "peso": v} for k, v in partes.items()]
    pesos = []
    for item in partes:
        if isinstance(item, dict):
            pesos.append(
                {
                    "nombre": str(item.get("nombre") or item.get("id") or "parte"),
                    "peso": float(item.get("peso") or item.get("acciones") or item.get("ha") or 0),
                }
            )
        else:
            pesos.append({"nombre": str(item), "peso": 1.0})
    suma = sum(p["peso"] for p in pesos) or 1.0
    asignaciones = [
        {
            "nombre": p["nombre"],
            "peso": p["peso"],
            "proporcion": round(p["peso"] / suma, 6),
            "asignado": round(total * p["peso"] / suma, 6),
        }
        for p in pesos
    ]
    return {"total": total, "suma_pesos": suma, "asignaciones": asignaciones}
'''

_SKILL_LAMINA = '''
def run(input_data):
    """Lámina de riego (mm) a partir de volumen (m³) y superficie (ha o m²)."""
    volumen_m3 = float(input_data.get("volumen_m3") or input_data.get("volumen") or 0)
    superficie_ha = input_data.get("superficie_ha") or input_data.get("ha")
    superficie_m2 = input_data.get("superficie_m2") or input_data.get("m2")
    if superficie_ha is not None:
        area_m2 = float(superficie_ha) * 10000.0
        ha = float(superficie_ha)
    else:
        area_m2 = float(superficie_m2 or 0)
        ha = area_m2 / 10000.0 if area_m2 else 0.0
    lamina_mm = (volumen_m3 / area_m2) * 1000.0 if area_m2 else 0.0
    return {
        "volumen_m3": volumen_m3,
        "superficie_m2": area_m2,
        "superficie_ha": round(ha, 4),
        "lamina_mm": round(lamina_mm, 3),
        "formula": "lámina_mm = (volumen_m3 / área_m2) * 1000",
    }
'''

_SKILL_TIEMPO = '''
def run(input_data):
    """Tiempo de riego a partir de volumen (m³) y caudal (L/s o m³/s)."""
    volumen_m3 = float(input_data.get("volumen_m3") or input_data.get("volumen") or 0)
    caudal_ls = input_data.get("caudal_ls") or input_data.get("l_s")
    caudal_m3s = input_data.get("caudal_m3s") or input_data.get("m3_s")
    if caudal_ls is not None:
        q_m3s = float(caudal_ls) / 1000.0
    else:
        q_m3s = float(caudal_m3s or 0)
    segundos = volumen_m3 / q_m3s if q_m3s else 0.0
    horas = segundos / 3600.0
    return {
        "volumen_m3": volumen_m3,
        "caudal_m3s": round(q_m3s, 8),
        "caudal_ls": round(q_m3s * 1000, 4),
        "tiempo_s": round(segundos, 1),
        "tiempo_h": round(horas, 4),
        "tiempo_hm": {
            "horas": int(horas),
            "minutos": int(round((horas - int(horas)) * 60)),
        },
    }
'''

_SKILL_DOCX = '''
def run(input_data):
    """Genera un archivo Word (.docx) con título y contenido en texto plano."""
    import base64
    from io import BytesIO
    from docx import Document

    title = str(input_data.get("titulo") or input_data.get("title") or "Documento Irrigación")
    content = str(
        input_data.get("contenido")
        or input_data.get("content")
        or input_data.get("texto")
        or input_data.get("body")
        or ""
    )
    filename = str(input_data.get("filename") or input_data.get("nombre") or f"{title}.docx")
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    doc = Document()
    doc.add_heading(title, level=0)
    for block in content.replace("\\r\\n", "\\n").split("\\n"):
        line = block.strip()
        if line:
            doc.add_paragraph(line)

    buf = BytesIO()
    doc.save(buf)
    raw = buf.getvalue()
    return {
        "filename": filename,
        "content_base64": base64.b64encode(raw).decode("ascii"),
        "size_bytes": len(raw),
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
'''

CATALOG: list[SkillRecord] = [
    {
        "id": "caudal_canal",
        "name": "Cálculo de caudal (Q = A·v)",
        "description": (
            "Calcula el caudal de un canal o toma a partir del área de la sección "
            "(m²) y la velocidad (m/s). Devuelve m³/s y L/s."
        ),
        "tags": ["caudal", "canal", "toma", "seccion", "velocidad", "q", "a", "v"],
        "code": _SKILL_CAUDAL.strip(),
    },
    {
        "id": "conversion_unidades",
        "name": "Conversión de unidades de caudal",
        "description": (
            "Convierte un caudal entre L/s, m³/s, m³/h y m³/día."
        ),
        "tags": ["conversion", "unidades", "l/s", "m3", "caudal", "equivalencia"],
        "code": _SKILL_CONVERSION.strip(),
    },
    {
        "id": "prorrateo_turno",
        "name": "Prorrateo de turno de riego",
        "description": (
            "Reparte un caudal o volumen total entre derechos, acciones o hectáreas."
        ),
        "tags": ["prorrateo", "turno", "reparto", "acciones", "derechos", "hectareas"],
        "code": _SKILL_PRORRATEO.strip(),
    },
    {
        "id": "lamina_riego",
        "name": "Lámina de riego",
        "description": (
            "Calcula la lámina aplicada en mm a partir del volumen (m³) y la superficie "
            "(ha o m²)."
        ),
        "tags": ["lamina", "riego", "milimetros", "volumen", "superficie", "hectareas"],
        "code": _SKILL_LAMINA.strip(),
    },
    {
        "id": "tiempo_riego",
        "name": "Tiempo de riego",
        "description": (
            "Calcula cuánto tiempo hay que regar para aplicar un volumen dado un caudal."
        ),
        "tags": ["tiempo", "duracion", "riego", "horas", "caudal", "volumen"],
        "code": _SKILL_TIEMPO.strip(),
    },
    {
        "id": "generar_documento_word",
        "name": "Generación de documento Word (.docx)",
        "description": (
            "Redacta y exporta un informe o documento institucional en formato Word (.docx) "
            "a partir de un título y el contenido en texto."
        ),
        "tags": [
            "word",
            "docx",
            "documento",
            "informe",
            "redactar",
            "exportar",
            "escribir",
            "archivo",
        ],
        "code": _SKILL_DOCX.strip(),
    },
]


APPROVAL_KIND_EXECUTE = "execute_local"
APPROVAL_KIND_DOWNLOAD = "download_remote"

_SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "caudal_canal": (
        "caudal",
        "q=",
        "q =",
        "area",
        "área",
        "velocidad",
        "seccion",
        "sección",
        "canal",
        "toma",
    ),
    "conversion_unidades": (
        "convert",
        "conversion",
        "conversión",
        "equival",
        "l/s",
        "m3/s",
        "m³/s",
        "m3/h",
        "m3/d",
        "pasame a",
        "pasá a",
        "pasa a",
        "unidades",
    ),
    "prorrateo_turno": (
        "prorrate",
        "repart",
        "reparto",
        "turno",
        "derechos",
        "acciones",
        "hectarea",
        "hectárea",
    ),
    "lamina_riego": ("lamina", "lámina", "milimetros", "milímetros", "mm de riego"),
    "tiempo_riego": (
        "tiempo de riego",
        "cuanto regar",
        "cuánto regar",
        "duracion",
        "duración",
        "horas de riego",
    ),
    "generar_documento_word": (
        "word",
        "docx",
        "documento",
        "informe",
        "redact",
        "exportar",
        "generar archivo",
        "armame",
        "armá",
        "escribime",
        "escribí",
    ),
}

_CALC_VERBS = (
    "calcul",
    "convert",
    "prorrate",
    "equival",
    "repart",
    "cuánto da",
    "cuanto da",
    "pasame a",
    "pasá a",
    "pasa a",
    "cuanto es",
    "cuánto es",
    "dame el",
    "decime cu",
)

_UNCERTAINTY_MARKERS = (
    "no puedo calcular",
    "no tengo una herramienta",
    "no dispongo de",
    "no puedo hacer ese cálculo",
    "necesitaría datos numéricos",
    "faltan datos",
    "no encontré una skill",
    "reformulá con números",
)


def should_try_skill_marketplace(text: str, assistant_reply: str | None = None) -> bool:
    """Determina si conviene buscar en el marketplace antes de responder."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return False

    if any(kw in lowered for keywords in _SKILL_KEYWORDS.values() for kw in keywords):
        return True
    if any(verb in lowered for verb in _CALC_VERBS):
        return True
    if re.search(r"\d", lowered) and any(
        term in lowered
        for term in ("caudal", "riego", "convert", "prorrate", "lamina", "lámina", "m3", "l/s")
    ):
        return True

    if assistant_reply:
        reply_lower = assistant_reply.lower()
        if any(marker in reply_lower for marker in _UNCERTAINTY_MARKERS):
            return True
    return False


_ACTION_REQUEST_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bpod[eé]s\b",
        r"\bpodes\b",
        r"\bpuede[s]?\s+hacer",
        r"\bsabr[eé]s\b",
        r"\bsabes\b",
        r"\bhac[eé]lo\b",
        r"\bhac[eé]\s",
        r"\bhace\s",
        r"\bquiero que\b",
        r"\bnecesito que\b",
        r"\bme pod[eé]s\b",
        r"\bme podes\b",
        r"\btien[eé]s\s+(?:alguna|una)\s+(?:skill|habilidad|herramienta)",
        r"\bpod[eé]s\s+(?:calcular|convertir|generar|exportar|redactar|armar)",
    )
)


def is_action_request(text: str) -> bool:
    """Detecta pedidos del tipo 'hacé esto' o '¿podés hacer esto?'."""
    lowered = (text or "").lower().strip()
    if not lowered:
        return False
    if should_try_skill_marketplace(text):
        return True
    return any(pattern.search(lowered) for pattern in _ACTION_REQUEST_PATTERNS)


def looks_like_skill_intent(text: str) -> bool:
    """Heurística amplia: cálculos, conversiones, automatizaciones y documentos."""
    return is_action_request(text)


def match_catalog_by_keywords(text: str) -> dict[str, Any] | None:
    """Coincidencia directa de palabras clave del usuario contra skills locales."""
    lowered = (text or "").lower()
    best: SkillRecord | None = None
    best_score = 0
    for skill in CATALOG:
        score = 0
        for keyword in _SKILL_KEYWORDS.get(skill["id"], ()):
            if keyword in lowered:
                score += 2
        for tag in skill["tags"]:
            if len(tag) >= 3 and tag in lowered:
                score += 1
        if score > best_score:
            best_score = score
            best = skill
    if best is None or best_score < 2:
        return None
    return search_catalog(best["name"], infer_arguments(best["id"], text))


def find_local_skill(task: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Busca una skill instalada que pueda resolver la tarea."""
    keyword_hit = match_catalog_by_keywords(task)
    if keyword_hit and keyword_hit.get("found"):
        return keyword_hit
    result = search_catalog(task, arguments or {"query": task})
    if result.get("found"):
        score = int(result.get("score") or 0)
        if score >= 2 or is_action_request(task):
            return result
    return {**result, "found": False}


def download_remote_prompt() -> str:
    return (
        "No puedo hacer eso que me pediste. "
        "¿Querés que descargue la habilidad desde internet?"
    )


def _extract_numbers(text: str) -> list[float]:
    raw = re.findall(r"(\d+(?:[.,]\d+)?)", text or "")
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item.replace(",", ".")))
        except ValueError:
            continue
    return out


def infer_arguments(skill_id: str, user_message: str) -> dict[str, Any]:
    """Inferencia heurística de argumentos cuando el LLM no los extrajo."""
    text = user_message or ""
    lowered = text.lower()
    numbers = _extract_numbers(text)
    args: dict[str, Any] = {"query": text}

    if skill_id == "caudal_canal":
        if len(numbers) >= 2:
            args["area_m2"] = numbers[0]
            args["velocidad_ms"] = numbers[1]
        elif len(numbers) == 1:
            if any(k in lowered for k in ("area", "área", "m2", "m²", "seccion", "sección")):
                args["area_m2"] = numbers[0]
            else:
                args["velocidad_ms"] = numbers[0]
    elif skill_id == "conversion_unidades":
        if numbers:
            args["valor"] = numbers[0]
        for unit in ("l/s", "l/s", "m3/s", "m³/s", "m3/h", "m3/d", "m3/dia", "m3/día"):
            if unit.replace("³", "3") in lowered.replace("³", "3"):
                args["unidad"] = unit
                break
    elif skill_id == "prorrateo_turno":
        if numbers:
            args["total"] = numbers[0]
        pesos = re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:ha|acciones?|derechos?)", lowered)
        if pesos:
            args["partes"] = [{"nombre": f"parte_{i+1}", "peso": float(p.replace(",", "."))} for i, p in enumerate(pesos)]
    elif skill_id == "lamina_riego":
        if numbers:
            args["volumen_m3"] = numbers[0]
            if len(numbers) > 1:
                if "ha" in lowered:
                    args["superficie_ha"] = numbers[1]
                else:
                    args["superficie_m2"] = numbers[1]
    elif skill_id == "tiempo_riego":
        if numbers:
            args["volumen_m3"] = numbers[0]
            if len(numbers) > 1:
                if "l/s" in lowered or "l/s" in lowered:
                    args["caudal_ls"] = numbers[1]
                else:
                    args["caudal_m3s"] = numbers[1]
    elif skill_id == "generar_documento_word":
        title_match = re.search(r"(?:titulo|título|informe|documento)\s*[:\-]?\s*(.+)", text, re.I)
        args["titulo"] = (title_match.group(1).strip()[:120] if title_match else "Documento Irrigación")
        args["contenido"] = text
    return args


def enrich_skill_arguments(skill: dict[str, Any], user_message: str) -> dict[str, Any]:
    """Completa argumentos faltantes antes de ejecutar la skill."""
    skill_id = str(skill.get("id") or "")
    current = dict(skill.get("arguments") or {})
    inferred = infer_arguments(skill_id, user_message)
    merged = {**inferred, **{k: v for k, v in current.items() if v not in (None, "", {})}}
    if skill_id == "generar_documento_word":
        if not merged.get("contenido") and not merged.get("content"):
            merged["contenido"] = user_message
        if not merged.get("titulo") and not merged.get("title"):
            merged["titulo"] = "Documento Irrigación"
    return merged


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúüñ0-9/]+", (text or "").lower()))


def search_catalog(task: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Busca la skill más pertinente en el catálogo institucional."""
    tokens = _tokenize(task)
    lowered_task = (task or "").lower()
    best: SkillRecord | None = None
    best_score = 0
    for skill in CATALOG:
        haystack = " ".join(
            [skill["id"], skill["name"], skill["description"], " ".join(skill["tags"])]
        ).lower()
        score = sum(1 for token in tokens if token in haystack)
        if skill["id"] in lowered_task or skill["name"].lower() in lowered_task:
            score += 4
        for keyword in _SKILL_KEYWORDS.get(skill["id"], ()):
            if keyword in lowered_task:
                score += 2
        if score > best_score:
            best_score = score
            best = skill
    if best is None or best_score < 1:
        return {
            "found": False,
            "query": task,
            "available": [
                {"id": s["id"], "name": s["name"], "description": s["description"]}
                for s in CATALOG
            ],
        }
    resolved_args = arguments or {}
    if best["id"] == "generar_documento_word" or not any(
        k not in {"query", "raw", "valor"} for k in resolved_args
    ):
        resolved_args = {**infer_arguments(best["id"], task), **resolved_args}
    return {
        "found": True,
        "id": best["id"],
        "name": best["name"],
        "description": best["description"],
        "code": best["code"],
        "arguments": resolved_args,
        "score": best_score,
    }


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"valor": data}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {"valor": raw}


@tool
def search_skill_marketplace(task: str, arguments_json: str = "{}") -> str:
    """Busca en el catálogo institucional una skill (herramienta Python) para la tarea.

    Usala cuando el usuario pide un cálculo, conversión, prorrateo, lámina o tiempo de riego,
    generación de documentos Word, o cualquier automatización que no puedas resolver solo
    con el contexto RAG. No inventes números: primero buscá la skill.

    Args:
        task: descripción breve de la tarea (ej. 'calcular caudal con área y velocidad').
        arguments_json: JSON con los números/datos extraídos del mensaje del usuario.
    """
    result = search_catalog(task, _parse_arguments(arguments_json))
    public = {k: v for k, v in result.items() if k != "code"}
    if result.get("found"):
        public["has_code"] = True
    return json.dumps(public, ensure_ascii=False)
