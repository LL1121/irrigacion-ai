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
]


def looks_like_skill_intent(text: str) -> bool:
    """Heurística para cálculos/automatizaciones que requieren una skill."""
    lowered = (text or "").lower()
    has_number = bool(re.search(r"\d", lowered))
    verbs = (
        "calcul",
        "convert",
        "prorrate",
        "equival",
        "repart",
        "cuánto da",
        "cuanto da",
        "pasame a",
        "pasá a",
        "pasa a l",
        "pasa a m",
    )
    return has_number and any(verb in lowered for verb in verbs)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúüñ0-9/]+", (text or "").lower()))


def search_catalog(task: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Busca la skill más pertinente en el catálogo institucional."""
    tokens = _tokenize(task)
    best: SkillRecord | None = None
    best_score = 0
    for skill in CATALOG:
        haystack = " ".join(
            [skill["id"], skill["name"], skill["description"], " ".join(skill["tags"])]
        ).lower()
        score = sum(1 for token in tokens if token in haystack)
        if skill["id"] in (task or "").lower() or skill["name"].lower() in (task or "").lower():
            score += 4
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
    return {
        "found": True,
        "id": best["id"],
        "name": best["name"],
        "description": best["description"],
        "code": best["code"],
        "arguments": arguments or {},
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

    Usala cuando el usuario pide un cálculo, conversión o automatización y no hay
    una herramienta local bindeada para resolverlo. No inventes números: primero
    buscá la skill.

    Args:
        task: descripción breve de la tarea (ej. 'calcular caudal con área y velocidad').
        arguments_json: JSON con los números/datos extraídos del mensaje del usuario.
    """
    result = search_catalog(task, _parse_arguments(arguments_json))
    public = {k: v for k, v in result.items() if k != "code"}
    if result.get("found"):
        public["has_code"] = True
    return json.dumps(public, ensure_ascii=False)
