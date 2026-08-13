"""Enrutado de órdenes: el objeto del pedido manda, no el primer regex."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GOOGLE_ACTIONS = {
    "calendar_list": {"tool_id": "calendar.list", "write": False},
    "calendar_create": {"tool_id": "calendar.create", "write": True},
    "gmail_list": {"tool_id": "gmail.list", "write": False},
    "gmail_send": {"tool_id": "gmail.send", "write": True},
    "drive_search": {"tool_id": "drive.search", "write": False},
    "drive_read": {"tool_id": "drive.read", "write": False},
    "drive_index": {"tool_id": "drive.index", "write": False},
}

_MAIL_OBJ_RE = re.compile(
    r"\b(?:mails?|correos?|e-?mails?|gmail|inbox|bandeja)\b",
    re.I,
)
_CAL_OBJ_RE = re.compile(
    r"\b(?:calendario|agenda|evento|reuni[oó]n(?:es)?|cita|llamada)\b",
    re.I,
)
_DRIVE_OBJ_RE = re.compile(
    r"\b(?:google\s+drive|\bdrive\b|archivos?\s+de\s+drive)\b",
    re.I,
)
_SEND_RE = re.compile(
    r"(?:envi(?:á|a|ar)|mand(?:á|a|ar)|redact(?:á|a|ar)|"
    r"program(?:á|a|ar|arme|ame).{0,30}env[ií]o|"
    r"program(?:á|a|ar|arme|ame).{0,20}(?:un\s+)?(?:mail|correo|email))",
    re.I,
)
_CAL_CREATE_RE = re.compile(
    r"(?:agend(?:á|ar)\b|crear\s+(?:un\s+)?evento|"
    r"bloque(?:á|a|ar)\s+en\s+el\s+calendario|"
    r"program(?:á|a|ar).{0,20}(?:evento|reuni[oó]n|cita|en\s+(?:el\s+)?calendario))",
    re.I,
)
_CAL_LIST_RE = re.compile(
    r"(?:qu[eé]\s+tengo\s+en\s+(?:la\s+)?(?:agenda|calendario)|"
    r"mis\s+eventos|pr[oó]xim[oa]s?\s+eventos|"
    r"(?:mostr(?:á|a|ar)|list(?:á|a|ar)|revis(?:á|a|ar))\s+"
    r"(?:la\s+)?(?:agenda|calendario|eventos))",
    re.I,
)
_GMAIL_LIST_RE = re.compile(
    r"(?:revis(?:á|a|ar)|list(?:á|a|ar)|mostr(?:á|a|ar)|le[eé]).{0,20}"
    r"(?:mails?|correos?|inbox|bandeja|gmail)|"
    r"(?:inbox|bandeja\s+de\s+entrada|correos?\s+recientes)",
    re.I,
)
_DRIVE_SEARCH_RE = re.compile(
    r"(?:busc(?:á|a|ar)\s+en\s+drive|en\s+mi\s+drive|archivos?\s+de\s+drive)",
    re.I,
)
_DRIVE_INDEX_RE = re.compile(
    r"(?:index(?:á|a|ar)|guard(?:á|a|ar)\s+(?:en|como)\s+contexto).{0,40}"
    r"(?:drive|archivo|documento)",
    re.I,
)
_DRIVE_READ_RE = re.compile(
    r"(?:le[eé]|abr[ií])\s+(?:el\s+)?(?:archivo|documento|doc)",
    re.I,
)
_COMMAND_RE = re.compile(
    r"(?:pod[eé]s|podes|podr[ií]as?|quer[eé]s|quiero|necesit|"
    r"hac[eé]|program|agend|envi|mand|cre[aá]|busc|list|"
    r"le[eé]|abr[ií]|guard|anot|revis|mostr|redact|index)",
    re.I,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class CommandDecision:
    action: str
    ask: str | None = None
    source: str = "heuristic"

    def as_google_intent(self) -> dict[str, Any] | None:
        meta = GOOGLE_ACTIONS.get(self.action)
        if not meta:
            return None
        return {
            "tool_id": meta["tool_id"],
            "action": self.action,
            "write": meta["write"],
        }


def looks_like_command(text: str) -> bool:
    return bool(_COMMAND_RE.search(text or ""))


def looks_like_native_google(text: str) -> bool:
    """Mail / Calendar / Drive: tools nativas, nunca una skill descargada."""
    blob = text or ""
    return (
        _has_mail_object(blob) or _has_cal_object(blob) or _has_drive_object(blob)
    )


def should_use_native_google(
    message: str,
    context: str = "",
    *,
    tool_called: bool = False,
) -> bool:
    if tool_called:
        return True
    if looks_like_native_google(message):
        return True
    if not looks_like_native_google(context or ""):
        return False
    if re.search(
        r"\b(?:caudal|padr[oó]n|l[aá]mina|punto\s+\d|riego|expediente)\b",
        message or "",
        re.I,
    ) and not looks_like_native_google(message):
        return False
    return bool(
        looks_like_command(message)
        or _EMAIL_RE.search(message or "")
        or re.search(
            r"asunto|decile|faltan|datos|minuto|hora|program|autoriz",
            message or "",
            re.I,
        )
    )


def infer_google_action(text: str) -> str | None:
    heuristic = heuristic_route(text)
    if heuristic and heuristic.action in GOOGLE_ACTIONS:
        return heuristic.action
    blob = text or ""
    if _has_mail_object(blob):
        if _SEND_RE.search(blob) or re.search(r"program", blob, re.I):
            return "gmail_send"
        return "gmail_list"
    if _has_cal_object(blob):
        if _CAL_CREATE_RE.search(blob) or re.search(r"agend", blob, re.I):
            return "calendar_create"
        return "calendar_list"
    if _has_drive_object(blob):
        if _DRIVE_INDEX_RE.search(blob):
            return "drive_index"
        if _DRIVE_READ_RE.search(blob):
            return "drive_read"
        return "drive_search"
    return None


def _has_mail_object(text: str) -> bool:
    return bool(_MAIL_OBJ_RE.search(text or ""))


def _has_cal_object(text: str) -> bool:
    return bool(_CAL_OBJ_RE.search(text or ""))


def _has_drive_object(text: str) -> bool:
    return bool(_DRIVE_OBJ_RE.search(text or ""))


def missing_google_slots(
    action: str,
    text: str,
    args: dict[str, Any] | None = None,
) -> str | None:
    """Si falta un dato crítico, no ejecutar: preguntar."""
    extra = args or {}
    blob = " ".join(
        str(extra.get(key) or "")
        for key in ("to", "subject", "body", "summary", "start_iso", "file_id", "search")
    )
    combined = f"{text or ''} {blob}".strip()
    if action == "gmail_send":
        if not _EMAIL_RE.search(combined) and not str(extra.get("to") or "").strip():
            return (
                "Dale, te armo el mail. Necesito: **a quién** (email), "
                "**asunto** y **qué tiene que decir**. "
                "Si lo querés para más tarde, decime el día y la hora: "
                "si no me decís horario, no lo mando."
            )
        wants_later = bool(
            re.search(
                r"program|más\s+tarde|mas\s+tarde|en\s+\d+|a\s+las",
                combined,
                re.I,
            )
        )
        has_when = bool(extra.get("send_at")) or bool(
            re.search(
                r"(?:en|dentro\s+de)\s+\d+\s+(?:min|hora|d[ií]a)|"
                r"a\s+las\s+\d|ahora|ya\s+mismo",
                combined,
                re.I,
            )
        )
        if wants_later and not has_when:
            return (
                "¿Lo mando **ahora** o lo programo? Si es programado, "
                "decime en cuánto (ej. en 5 minutos) o a qué hora."
            )
    if action == "calendar_create":
        if not _has_cal_object(combined) and not str(extra.get("summary") or "").strip():
            return (
                "¿Lo agendo en Calendar? Decime **título**, **día y hora**. "
                "Si en realidad era un mail u otra cosa, aclarámelo."
            )
        if not extra.get("start_iso") and not re.search(
            r"(?:\d|hoy|mañana|lunes|martes|mi[eé]rcoles|jueves|viernes|"
            r"s[aá]bado|domingo|a\s+las)",
            combined,
            re.I,
        ):
            return (
                "¿Cuándo lo agendo y con qué título? "
                "Con eso te armo el evento."
            )
    if action == "drive_read" and not (
        extra.get("file_id") or re.search(r"\b[A-Za-z0-9_-]{10,}\b", combined)
    ):
        return "Pasame el nombre o el ID del archivo de Drive que querés leer."
    return None


def _score_intents(text: str) -> dict[str, float]:
    scores: dict[str, float] = {key: 0.0 for key in GOOGLE_ACTIONS}
    mail = _has_mail_object(text)
    cal = _has_cal_object(text)
    drive = _has_drive_object(text)

    if mail and _SEND_RE.search(text or ""):
        scores["gmail_send"] += 4.0
    if mail and _GMAIL_LIST_RE.search(text or ""):
        scores["gmail_list"] += 3.0
    if mail and not _SEND_RE.search(text or "") and re.search(
        r"(?:mails?|correos?|gmail|inbox)", text or "", re.I
    ):
        scores["gmail_list"] += 1.2

    if cal and _CAL_CREATE_RE.search(text or ""):
        scores["calendar_create"] += 4.0
    if _CAL_LIST_RE.search(text or ""):
        scores["calendar_list"] += 3.5
    if cal and re.search(r"agend(?:á|ar)", text or "", re.I) and not mail:
        scores["calendar_create"] += 2.0

    if _DRIVE_INDEX_RE.search(text or ""):
        scores["drive_index"] += 4.5
        scores["drive_search"] = 0.0
    elif drive and _DRIVE_SEARCH_RE.search(text or ""):
        scores["drive_search"] += 3.5
    if drive and _DRIVE_READ_RE.search(text or "") and scores["drive_index"] == 0:
        scores["drive_read"] += 3.0

    # El objeto desempata: programar un MAIL no es Calendar.
    if mail and not cal:
        scores["calendar_create"] = 0.0
        scores["calendar_list"] *= 0.2
    if cal and not mail:
        scores["gmail_send"] *= 0.2
        scores["gmail_list"] *= 0.2
    if mail and cal:
        if re.search(r"env[ií]o|mail|correo|email", text or "", re.I):
            scores["calendar_create"] *= 0.15
        if re.search(r"evento|reuni[oó]n|calendario", text or "", re.I):
            scores["gmail_send"] *= 0.15

    return scores


def _best_intent(scores: dict[str, float]) -> tuple[str | None, float, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < 2.4:
        return None, best_score, second
    if best_score - second < 1.0:
        return None, best_score, second
    return best_name, best_score, second


def heuristic_route(text: str) -> CommandDecision | None:
    scores = _score_intents(text or "")
    best, _score, _second = _best_intent(scores)
    if not best:
        if looks_like_command(text) and (
            _has_mail_object(text) or _has_cal_object(text) or _has_drive_object(text)
        ):
            return CommandDecision(
                action="clarify",
                ask=(
                    "No quiero equivocarme: ¿lo que necesitás es un **mail**, "
                    "un **evento de Calendar**, o algo de **Drive**? "
                    "Tirame el dato concreto (destinatario, título, archivo)."
                ),
                source="heuristic",
            )
        return None
    ask = missing_google_slots(best, text or "")
    if ask:
        return CommandDecision(action="clarify", ask=ask, source="heuristic")
    return CommandDecision(action=best, source="heuristic")


def _llm_route(text: str, history: list[dict] | None = None) -> CommandDecision | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    hist_bits: list[str] = []
    for item in (history or [])[-6:]:
        role = (item.get("role") or "").lower()
        msg = (item.get("message") or "").strip()
        if msg:
            hist_bits.append(f"{role}: {msg[:240]}")
    thread = "\n".join(hist_bits) if hist_bits else "(sin historial)"
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        temperature=0,
    )
    prompt = (
        "Clasificá la última orden del usuario para un asistente de oficina.\n"
        "Acciones válidas: calendar_list, calendar_create, gmail_list, gmail_send, "
        "drive_search, drive_read, drive_index, clarify, none.\n"
        "Reglas:\n"
        "- El objeto manda: mail/correo/email → Gmail; evento/agenda/calendario → Calendar; "
        "Drive/archivo → Drive.\n"
        "- 'Programar el envío de un mail' es gmail_send (o clarify si falta destinatario), "
        "NUNCA calendar_create.\n"
        "- Charla, saludos o preguntas de documentos/riego → none.\n"
        "- Si falta un dato imprescindible, clarify y preguntá en español rioplatense.\n"
        "Respondé SOLO JSON: {\"action\":\"...\",\"ask\":null}\n\n"
        f"Historial:\n{thread}\n\nOrden:\n{text}"
    )
    try:
        response = llm.invoke(
            [
                SystemMessage(content="Devolvé JSON válido, sin markdown."),
                HumanMessage(content=prompt),
            ]
        )
        raw = (getattr(response, "content", None) or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.I | re.M).strip()
        data = json.loads(raw)
        action = str(data.get("action") or "none").strip()
        ask = data.get("ask")
        ask_text = str(ask).strip() if ask else None
        if action not in GOOGLE_ACTIONS and action not in {"clarify", "none"}:
            return None
        if action == "none":
            return CommandDecision(action="none", source="llm")
        if action == "clarify":
            return CommandDecision(
                action="clarify",
                ask=ask_text
                or "¿Me precisás un poco más qué hay que hacer (mail, evento o Drive)?",
                source="llm",
            )
        slot_ask = missing_google_slots(action, text)
        if slot_ask:
            return CommandDecision(action="clarify", ask=slot_ask, source="llm")
        return CommandDecision(action=action, source="llm")
    except Exception:
        logger.exception("No pude clasificar la orden con el LLM")
        return None


def resolve_command_intent(
    text: str,
    history: list[dict] | None = None,
) -> CommandDecision:
    """Decide tool Google, preguntar, o none (sigue el plan RAG/skills)."""
    heuristic = heuristic_route(text)
    if heuristic and heuristic.action in GOOGLE_ACTIONS:
        return heuristic

    googleish = (
        _has_mail_object(text) or _has_cal_object(text) or _has_drive_object(text)
    )
    # Ya sabemos la tool y solo faltan datos: no gastes un LLM.
    if (
        heuristic
        and heuristic.action == "clarify"
        and heuristic.ask
        and "¿lo que necesitás es un" not in heuristic.ask
    ):
        return heuristic

    if googleish or (heuristic and heuristic.action == "clarify"):
        llm = _llm_route(text, history)
        if llm and llm.action != "none":
            return llm
        if heuristic:
            return heuristic
        if llm:
            return llm
    return CommandDecision(action="none", source="none")


@tool
def use_google(
    action: str,
    query: str = "",
    to: str = "",
    subject: str = "",
    body: str = "",
    summary: str = "",
    start_iso: str = "",
    end_iso: str = "",
    search: str = "",
    file_id: str = "",
    send_at: str = "",
) -> str:
    """Usá Calendar, Gmail o Drive de la cuenta Google del usuario.

    PRIORIDAD: mail/correo/Gmail, agenda/evento o Drive SIEMPRE van acá.
    NUNCA uses search_skill_marketplace para enviar o programar un mail.
    El objeto manda: mail → gmail_send/gmail_list; evento → calendar_*;
    Drive → drive_*. 'Programar el envío de un mail' es gmail_send.
    Si pidió espera (en 5 minutos, a las 18), pasá send_at en ISO-8601
    y NO lo mandes como si fuera ahora.
    Si falta destinatario o el horario de un envío programado, preguntá.

    Acciones: calendar_list, calendar_create, gmail_list, gmail_send,
    drive_search, drive_read, drive_index.
    """
    return json.dumps(
        {
            "action": action,
            "query": query,
            "to": to,
            "subject": subject,
            "body": body,
            "summary": summary,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "search": search,
            "file_id": file_id,
            "send_at": send_at,
        },
        ensure_ascii=False,
    )


@tool
def save_user_context(note: str, scope: str = "") -> str:
    """Guardá una nota persistente SOLO si el usuario lo pidió explícito.

    Ejemplos válidos: 'guardá esto como contexto', 'anotá que…',
    'recordá que mañana hay corte'.
    NUNCA la uses en saludos, 'cómo andás', chistes, preguntas, ni
    follow-ups de otra tarea. Si no hay verbo de guardar/anotar/recordar,
    no llames esta tool: respondé el chat.
    scope: 'personal', 'irrigacion', o '' si todavía no lo dijo.
    """
    return json.dumps({"note": note, "scope": scope}, ensure_ascii=False)
