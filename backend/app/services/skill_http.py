"""HTTP controlado para skills: solo hosts permitidos / URLs del pedido."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)

# Dominios institucionales siempre permitidos (telemetría / servicios web DGI).
_DEFAULT_ALLOW_SUFFIXES = (
    "irrigacion.gov.ar",
    "cloud.irrigacion.gov.ar",
)


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in _URL_RE.findall(text or ""):
        cleaned = match.rstrip(".,;:)")
        if cleaned not in found:
            found.append(cleaned)
    return found


def _host_allowed(host: str, allowed_hosts: set[str], allowed_suffixes: tuple[str, ...]) -> bool:
    host = (host or "").lower().strip().rstrip(".")
    if not host:
        return False
    if host in allowed_hosts:
        return True
    for suffix in allowed_suffixes:
        suf = suffix.lower().lstrip(".")
        if host == suf or host.endswith("." + suf):
            return True
    return False


def _is_public_hostname(host: str) -> bool:
    """Rechaza IPs privadas/loopback literales."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def build_fetch_url(
    *,
    extra_allowed_urls: list[str] | None = None,
    timeout_s: float = 25.0,
    max_bytes: int = 2_500_000,
):
    """
    Devuelve una función fetch_url(url, method='GET') inyectable en el namespace
    de la skill. Solo permite http(s) hacia hosts allowlisted.
    """
    settings = get_settings()
    configured = tuple(
        s.strip()
        for s in (getattr(settings, "skill_http_allow_suffixes", "") or "").split(",")
        if s.strip()
    )
    suffixes = configured or _DEFAULT_ALLOW_SUFFIXES

    allowed_hosts: set[str] = set()
    for raw in extra_allowed_urls or []:
        try:
            host = urlparse(raw).hostname
            if host:
                allowed_hosts.add(host.lower())
        except Exception:
            continue

    def fetch_url(
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        target = str(url or "").strip()
        if not target:
            return {"ok": False, "error": "URL vacía"}
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"}:
            return {"ok": False, "error": f"Esquema no permitido: {parsed.scheme}"}
        host = (parsed.hostname or "").lower()
        if not _is_public_hostname(host):
            return {"ok": False, "error": "Host no permitido (IP privada/local)"}
        if not _host_allowed(host, allowed_hosts, suffixes):
            return {
                "ok": False,
                "error": (
                    f"Host '{host}' no está en la allowlist. "
                    f"Permitidos: URLs del pedido + {', '.join(suffixes)}"
                ),
            }

        req_headers = {
            "User-Agent": "IrrigacionBot/1.0 (+skill-fetch)",
            "Accept": "*/*",
        }
        if headers:
            for key, value in headers.items():
                if str(key).lower() in {"host", "authorization", "cookie"}:
                    continue
                req_headers[str(key)] = str(value)

        request = Request(target, method=(method or "GET").upper(), headers=req_headers)
        try:
            with urlopen(request, timeout=timeout_s) as resp:  # noqa: S310
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    return {
                        "ok": False,
                        "error": f"Respuesta demasiado grande (>{max_bytes} bytes)",
                        "status": getattr(resp, "status", None),
                    }
                charset = resp.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                content_type = resp.headers.get("Content-Type", "")
                parsed_json = None
                if "json" in content_type.lower() or text.lstrip().startswith(("[", "{")):
                    try:
                        parsed_json = json.loads(text)
                    except json.JSONDecodeError:
                        parsed_json = None
                return {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "url": target,
                    "content_type": content_type,
                    "text": text,
                    "json": parsed_json,
                    "bytes": len(raw),
                }
        except HTTPError as exc:
            body = exc.read(max_bytes) if hasattr(exc, "read") else b""
            return {
                "ok": False,
                "error": f"HTTP {exc.code}: {exc.reason}",
                "status": exc.code,
                "text": body.decode("utf-8", errors="replace"),
            }
        except URLError as exc:
            return {"ok": False, "error": f"Error de red: {exc.reason}"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("fetch_url falló para %s", target)
            return {"ok": False, "error": str(exc)}

    return fetch_url
