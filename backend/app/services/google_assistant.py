"""Intents y ejecución de tools Google (Calendar / Gmail / Drive) para el agente."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.auth_session import add_tool_whitelist, is_tool_whitelisted
from app.services.command_router import heuristic_route
from app.services.google_workspace import (
    calendar_create_event,
    calendar_list_events,
    drive_read_text_file,
    drive_search_files,
    gmail_list_messages,
    gmail_send_message,
    google_oauth_configured,
)
from app.services.response_normalize import looks_raw_technical

APPROVAL_KIND_GOOGLE_TOOL = "google_tool"

_DRIVE_SEARCH_RE = re.compile(
    r"(?:busc(?:á|a|ar)\s+en\s+drive|en\s+mi\s+drive|google\s+drive|archivos?\s+de\s+drive)",
    re.I,
)


def detect_google_intent(text: str) -> dict[str, Any] | None:
    """Heurística (sin LLM): tool Google clara, o clarify si el pedido es Google-ish."""
    decision = heuristic_route(text)
    if not decision:
        return None
    if decision.action == "clarify":
        return {"tool_id": "command.clarify", "action": "clarify", "write": False}
    return decision.as_google_intent()


def parse_send_at(text: str, explicit_iso: str | None = None) -> str | None:
    from app.services.order_parse import parse_run_at

    return parse_run_at(text, explicit_iso)


def _parse_simple_event(text: str) -> dict[str, Any]:
    """Heurística mínima: título + mañana 10:00 (1h) si no hay datos."""
    title_match = re.search(
        r"(?:evento|reuni[oó]n|llamada|cita)\s+(?:llamad[oa]\s+|sobre\s+|de\s+)?[«\"]?(.+?)[»\"]?(?:\s+el|\s+mañana|\s+hoy|$)",
        text,
        re.I,
    )
    title = (title_match.group(1).strip() if title_match else None) or "Evento Irrigación"
    title = re.sub(r"\s+", " ", title)[:120]
    now = datetime.now(timezone.utc).astimezone()
    start = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    if re.search(r"\bhoy\b", text, re.I):
        start = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if start < now:
            start += timedelta(hours=1)
    end = start + timedelta(hours=1)
    return {
        "summary": title,
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "description": text[:500],
    }


def _parse_email(text: str) -> dict[str, Any]:
    to_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    to = to_match.group(0) if to_match else ""
    subj_match = re.search(
        r"(?:asunto|subject)\s*(?:es|:|-)\s*[«\"']?(.+?)[»\"']?(?:\s+y\s+|\s*$)",
        text,
        re.I,
    )
    subject = (
        subj_match.group(1).strip()[:120]
        if subj_match
        else "Mensaje desde Irrigación AI"
    )
    body_match = re.search(
        r"(?:decile|decí|dice|cuerpo|mensaje(?:\s+es)?)\s*[:\-]?\s*(.+)$",
        text,
        re.I | re.S,
    )
    body = (body_match.group(1).strip() if body_match else text)[:4000]
    send_at = parse_send_at(text)
    result = {"to": to, "subject": subject, "body": body}
    if send_at:
        result["send_at"] = send_at
    return result


def build_pending_google_tool(
    intent: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    action = intent["action"]
    args: dict[str, Any] = {"query": user_message}
    if action == "calendar_create":
        args.update(_parse_simple_event(user_message))
    elif action == "gmail_send":
        args.update(_parse_email(user_message))
    elif action == "drive_search":
        args["search"] = re.sub(_DRIVE_SEARCH_RE, "", user_message).strip() or user_message
    elif action in {"drive_read", "drive_index"}:
        m = re.search(r"\b([A-Za-z0-9_-]{10,})\b", user_message)
        args["file_id"] = m.group(1) if m else ""
        if action == "drive_index" and not args["file_id"]:
            args["search"] = user_message
    return {
        "tool_id": intent["tool_id"],
        "action": action,
        "write": bool(intent.get("write")),
        "arguments": args,
        "name": intent["tool_id"],
        "description": f"Acción Google: {intent['tool_id']}",
    }


def humanize_google_result(action: str, data: Any) -> str:
    if action == "calendar_list":
        items = data or []
        if not items:
            return "No tenés eventos próximos en el calendario."
        lines = ["Estos son tus próximos eventos:"]
        for ev in items[:15]:
            lines.append(f"- **{ev.get('summary')}** — {ev.get('start')}")
        return "\n".join(lines)
    if action == "calendar_create":
        return (
            f"Listo: agendé **{data.get('summary')}**. "
            f"Lo podés ver en Calendar{' (' + data['htmlLink'] + ')' if data.get('htmlLink') else ''}."
        )
    if action == "gmail_list":
        items = data or []
        if not items:
            return "No encontré correos recientes con ese criterio."
        lines = ["Estos son los correos más recientes:"]
        for m in items[:12]:
            lines.append(
                f"- **{m.get('subject') or '(sin asunto)'}** — de {m.get('from') or '?'}"
            )
        return "\n".join(lines)
    if action == "gmail_send":
        if data.get("scheduled_for"):
            return (
                f"Quedó **programado** para **{data.get('scheduled_for')}**: "
                f"mail a **{data.get('to')}** con asunto «{data.get('subject')}». "
                "No lo mando ahora; sale solo a esa hora."
            )
        return (
            f"Listo: mandé el mail a **{data.get('to')}** "
            f"con asunto «{data.get('subject')}»."
        )
    if action == "drive_search":
        items = data or []
        if not items:
            return "No encontré archivos en Drive con esa búsqueda."
        lines = ["Encontré esto en Drive:"]
        for f in items[:12]:
            lines.append(f"- **{f.get('name')}** (`{f.get('id')}`)")
        return "\n".join(lines)
    if action == "drive_read":
        name = data.get("name") or "archivo"
        text = (data.get("text") or "").strip()
        preview = text[:1200] + ("…" if len(text) > 1200 else "")
        return f"Contenido de **{name}**:\n\n{preview}"
    if looks_raw_technical(str(data)):
        return "Listo: la acción de Google terminó, pero el resultado vino raro. Pedime el dato puntual."
    return str(data)


def execute_google_tool(
    db: Session,
    *,
    user_id: str,
    pending: dict[str, Any],
) -> str:
    if not google_oauth_configured():
        return "Google no está configurado en el servidor todavía."
    action = pending.get("action")
    args = pending.get("arguments") or {}
    if action == "calendar_list":
        data = calendar_list_events(db, user_id, days=7)
        return humanize_google_result(action, data)
    if action == "calendar_create":
        data = calendar_create_event(
            db,
            user_id,
            summary=str(args.get("summary") or "Evento"),
            start_iso=str(args.get("start_iso")),
            end_iso=str(args.get("end_iso")),
            description=args.get("description"),
        )
        add_tool_whitelist(db, user_id, "calendar.create")
        return humanize_google_result(action, data)
    if action == "gmail_list":
        data = gmail_list_messages(db, user_id, max_results=10)
        return humanize_google_result(action, data)
    if action == "gmail_send":
        to = str(args.get("to") or "").strip()
        if not to:
            return "Me falta el destinatario (un email) para mandar el correo."
        subject = str(args.get("subject") or "Mensaje")
        body = str(args.get("body") or "")
        send_at = parse_send_at(
            " ".join(
                str(args.get(key) or "")
                for key in ("query", "send_at", "run_at", "body", "subject")
            ),
            str(args.get("send_at") or args.get("run_at") or "") or None,
        )
        if send_at:
            from app.services.scheduled_jobs import enqueue_job

            when = datetime.fromisoformat(send_at)
            enqueue_job(
                db,
                user_id=user_id,
                session_id=str(args.get("session_id") or "") or None,
                kind="gmail_send",
                payload={"to": to, "subject": subject, "body": body},
                run_at=when,
            )
            add_tool_whitelist(db, user_id, "gmail.send")
            pretty = when.astimezone().strftime("%H:%M")
            return humanize_google_result(
                action,
                {"to": to, "subject": subject, "scheduled_for": pretty},
            )
        data = gmail_send_message(
            db,
            user_id,
            to=to,
            subject=subject,
            body=body,
        )
        add_tool_whitelist(db, user_id, "gmail.send")
        return humanize_google_result(action, data)
    if action == "drive_search":
        data = drive_search_files(db, user_id, query=str(args.get("search") or args.get("query") or ""))
        return humanize_google_result(action, data)
    if action == "drive_read":
        file_id = str(args.get("file_id") or "").strip()
        if not file_id:
            return "Necesito el ID del archivo de Drive para leerlo."
        data = drive_read_text_file(db, user_id, file_id)
        return humanize_google_result(action, data)
    if action == "drive_index":
        file_id = str(args.get("file_id") or "").strip()
        if not file_id:
            hits = drive_search_files(
                db, user_id, query=str(args.get("search") or args.get("query") or "")
            )
            if not hits:
                return "No encontré un archivo en Drive para indexar. Pasame el ID o un nombre más preciso."
            file_id = str(hits[0].get("id") or "")
        data = drive_read_text_file(db, user_id, file_id)
        return humanize_google_result("drive_read", data)
    return "No reconocí esa acción de Google."


def google_write_needs_hitl(db: Session, user_id: str, pending: dict[str, Any]) -> bool:
    if not pending.get("write"):
        return False
    return not is_tool_whitelisted(db, user_id, str(pending.get("tool_id") or ""))
