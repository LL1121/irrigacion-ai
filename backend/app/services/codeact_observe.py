"""Observaciones CodeAct: puro, sin Docker ni settings."""

from __future__ import annotations

from typing import Any


def codeact_execution_failed(result: dict[str, Any] | None) -> bool:
    """True si el script no corrió o terminó con error (incluye rechazo de auditoría)."""
    if not isinstance(result, dict):
        return True
    status = str(result.get("status") or "")
    if status in {"rejected", "audit_unavailable"}:
        return True
    execution = result.get("execution") or {}
    if execution.get("error"):
        return True
    if int(execution.get("exit_code") or 0) != 0:
        return True
    parsed = execution.get("parsed")
    if isinstance(parsed, dict) and parsed.get("success") is False:
        return True
    return False


def codeact_retryable(result: dict[str, Any] | None) -> bool:
    """Self-heal solo ante fallos de ejecución, no ante denegación de seguridad."""
    if not isinstance(result, dict):
        return True
    status = str(result.get("status") or "")
    if status in {"rejected", "audit_unavailable"}:
        return False
    return codeact_execution_failed(result)


def format_codeact_observation(result: dict[str, Any] | None) -> str:
    result = result or {}
    status = str(result.get("status") or "")
    audit = result.get("audit") or {}
    execution = result.get("execution") or {}
    if status == "rejected":
        return (
            "AUDITORÍA DENEGADA. No ejecutes más este enfoque inseguro. "
            f"Motivo: {audit.get('reason') or 'riesgo detectado'}."
        )
    if status == "audit_unavailable":
        return (
            "La API de auditoría está saturada. No reintentés código nuevo ahora; "
            "explicá al usuario que hay que probar en un rato."
        )
    stdout = str(execution.get("stdout") or "")
    stderr = str(execution.get("stderr") or "")
    err = str(execution.get("error") or "")
    exit_code = execution.get("exit_code")
    if codeact_execution_failed(result):
        parts = [
            "EL SCRIPT FALLÓ. Corregí el código y volvé a llamar execute_python_code.",
            f"exit_code={exit_code}",
        ]
        if err:
            parts.append(f"error: {err}")
        if stderr.strip():
            parts.append("stderr:\n" + stderr[-4000:])
        if stdout.strip():
            parts.append("stdout:\n" + stdout[-2000:])
        return "\n".join(parts)
    body = stdout.strip() or "(sin stdout; el script terminó OK)"
    return (
        "EL SCRIPT TERMINÓ BIEN. Respondé al usuario con este resultado, "
        "sin traceback:\n" + body[-6000:]
    )
