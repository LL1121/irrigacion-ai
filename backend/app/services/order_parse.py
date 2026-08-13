"""Parsea TODA la orden: cada parte cuenta, ninguna se tira."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DELAY_RE = re.compile(
    r"(?:en|dentro\s+de)\s+(\d+)\s+(minutos?|mins?|horas?|hs?|d[ií]as?)",
    re.I,
)
_CLOCK_RE = re.compile(r"a\s+las\s+(\d{1,2})(?::(\d{2}))?", re.I)
_SUBJECT_RE = re.compile(
    r"(?:asunto|subject)\s*(?:es|:|-)\s*[«\"']?(.+?)[»\"']?(?:\s+y\s+|\s*$)",
    re.I,
)
_BODY_RE = re.compile(
    r"(?:decile|decí|dice|cuerpo|que\s+diga|mensaje(?:\s+es)?)\s*[:\-]?\s*(.+)$",
    re.I | re.S,
)
_NOW_RE = re.compile(r"\b(?:ahora|ya\s+mismo|inmediatamente)\b", re.I)
_PROGRAM_RE = re.compile(
    r"program(?:á|a|ar|ame|arlo|arlo)|más\s+tarde|mas\s+tarde",
    re.I,
)
_WORD_RE = re.compile(r"\b(?:word|docx|documento\s+word)\b", re.I)
_MAIL_RE = re.compile(r"\b(?:mails?|correos?|e-?mails?|gmail)\b", re.I)
_CAL_RE = re.compile(
    r"\b(?:calendario|agenda|evento|reuni[oó]n(?:es)?|cita)\b",
    re.I,
)
_DO_RE = re.compile(
    r"\b(?:prend(?:é|er|as|a)|apag(?:á|ar)|encend(?:é|er)|despert(?:á|ar)|"
    r"wake|wol|arm(?:á|ar|ame)|gener(?:á|ar)|cre(?:á|ar)|envi(?:á|ar)|"
    r"mand(?:á|ar)|instal(?:á|ar)|configur(?:á|ar)|activ(?:á|ar)|"
    r"hac(?:é|er|eme)|ejecut(?:á|ar)|program(?:á|ar)|"
    r"necesito\s+que|quiero\s+que)\b",
    re.I,
)


@dataclass
class OrderParts:
    raw: str = ""
    when_iso: str | None = None
    when_label: str | None = None
    to: str | None = None
    subject: str | None = None
    body: str | None = None
    wants_mail: bool = False
    wants_calendar: bool = False
    wants_word: bool = False
    program: bool = False
    goal: str = ""
    notes: list[str] = field(default_factory=list)

    def as_overlay(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.to:
            out["to"] = self.to
        if self.subject:
            out["subject"] = self.subject
        if self.body:
            out["body"] = self.body
        if self.when_iso:
            out["send_at"] = self.when_iso
            out["run_at"] = self.when_iso
        return out

    def recap_lines(self) -> list[str]:
        lines: list[str] = []
        if self.wants_mail:
            lines.append("enviar un **mail**")
        if self.wants_calendar:
            lines.append("un **evento** de Calendar")
        if self.wants_word:
            lines.append("armar un **Word**")
        if self.goal and not (self.wants_mail or self.wants_word or self.wants_calendar):
            lines.append(self.goal)
        if self.to:
            lines.append(f"para **{self.to}**")
        if self.subject:
            lines.append(f"asunto «{self.subject}»")
        if self.body:
            preview = self.body.strip()
            if len(preview) > 80:
                preview = preview[:77] + "…"
            lines.append(f"que diga: {preview}")
        if self.when_label:
            lines.append(f"**{self.when_label}** (no ahora)")
        elif self.program:
            lines.append("programado (falta horario)")
        return lines

    def recap(self) -> str:
        bits = self.recap_lines()
        if not bits:
            return ""
        return "Tomé toda la orden: " + "; ".join(bits) + "."

    def commit_ack(self) -> str:
        """Confirmación de que la orden (incluido el horario) se va a cumplir."""
        goal = self.goal or "eso que pediste"
        if self.when_label:
            return f"Dale, **{self.when_label}** lo hacemos: {goal}."
        if self.program:
            return f"Dale, lo programamos: {goal}."
        return ""


def parse_run_at(text: str, explicit_iso: str | None = None) -> str | None:
    """ISO local de una espera pedida, o None si es ahora / no hay horario."""
    raw = (explicit_iso or "").strip()
    if raw:
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc).astimezone()
            if when > datetime.now().astimezone():
                return when.isoformat()
        except ValueError:
            pass
    blob = text or ""
    if _NOW_RE.search(blob):
        return None
    delay = _DELAY_RE.search(blob)
    if delay:
        qty = int(delay.group(1))
        unit = delay.group(2).lower()
        now = datetime.now().astimezone()
        if unit.startswith("min"):
            when = now + timedelta(minutes=qty)
        elif unit.startswith("h"):
            when = now + timedelta(hours=qty)
        else:
            when = now + timedelta(days=qty)
        return when.isoformat()
    clock = _CLOCK_RE.search(blob)
    if clock:
        now = datetime.now().astimezone()
        hour = int(clock.group(1))
        minute = int(clock.group(2) or 0)
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        return when.isoformat()
    return None


def _when_label(iso: str | None, text: str) -> str | None:
    if not iso:
        delay = _DELAY_RE.search(text or "")
        if delay:
            return f"en {delay.group(1)} {delay.group(2)}"
        return None
    try:
        when = datetime.fromisoformat(iso)
        delay = _DELAY_RE.search(text or "")
        clock = when.astimezone().strftime("%H:%M")
        if delay:
            return f"en {delay.group(1)} {delay.group(2)} (≈ {clock})"
        return f"a las {clock}"
    except ValueError:
        return iso


def extract_order_parts(*chunks: str | None) -> OrderParts:
    """Junta mensaje + historial y saca cada pieza de la orden.

    El primer chunk es el mensaje actual: el horario se toma de ahí,
    y del hilo solo si es la misma orden (no un pedido nuevo).
    """
    cleaned = [part.strip() for part in chunks if (part or "").strip()]
    current = cleaned[0] if cleaned else ""
    rest = "\n".join(cleaned[1:])
    raw = "\n".join(cleaned)
    when_iso = parse_run_at(current)
    if not when_iso and current and not _NOW_RE.search(current):
        same_task = (
            (
                (_MAIL_RE.search(current) or _EMAIL_RE.search(current))
                and _MAIL_RE.search(rest)
            )
            or (_WORD_RE.search(current) and _WORD_RE.search(rest))
            or (
                not _MAIL_RE.search(current)
                and not _WORD_RE.search(current)
                and not _CAL_RE.search(current)
                and len(current) < 220
                and bool(_DELAY_RE.search(rest) or _PROGRAM_RE.search(rest))
            )
        )
        if same_task:
            when_iso = parse_run_at(f"{rest}\n{current}")
    goal_src = current or raw
    goal = _DELAY_RE.sub("", goal_src)
    goal = _CLOCK_RE.sub("", goal)
    goal = re.sub(r"\s+", " ", goal).strip(" ,.")
    if len(goal) > 160:
        goal = goal[:157] + "…"
    to_match = _EMAIL_RE.search(raw)
    subj_match = _SUBJECT_RE.search(raw)
    body_match = _BODY_RE.search(raw)
    subject = subj_match.group(1).strip()[:120] if subj_match else None
    body = body_match.group(1).strip()[:4000] if body_match else None
    if body:
        body = re.sub(
            r"\s+y\s+program.*$",
            "",
            body,
            flags=re.I,
        ).strip()
    return OrderParts(
        raw=raw,
        when_iso=when_iso,
        when_label=_when_label(when_iso, raw),
        to=to_match.group(0) if to_match else None,
        subject=subject,
        body=body,
        wants_mail=bool(_MAIL_RE.search(raw)),
        wants_calendar=bool(_CAL_RE.search(raw)),
        wants_word=bool(_WORD_RE.search(raw)),
        program=bool(_PROGRAM_RE.search(raw) or when_iso),
        goal=goal,
    )


def looks_like_do_task(text: str) -> bool:
    """Pedido de HACER algo (prender PC, armar word, mandar mail), no una pregunta RAG."""
    blob = (text or "").strip()
    if not blob:
        return False
    return bool(_DO_RE.search(blob))


def merge_args_with_order(
    args: dict[str, Any] | None,
    parts: OrderParts,
) -> dict[str, Any]:
    """La orden del usuario gana si la tool se olvidó de un dato."""
    merged = dict(args or {})
    overlay = parts.as_overlay()
    for key, value in overlay.items():
        if value and not merged.get(key):
            merged[key] = value
    if parts.when_iso:
        merged["send_at"] = parts.when_iso
        merged["run_at"] = parts.when_iso
    return merged
