"""Ciclo de vida de skills: centinela, reintento de auditoría y permiso de red."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sandbox import sandbox_network_mode
from app.services.sentinel import (
    audit_skill_code,
    is_transient_audit_error,
    scan_skill_capabilities,
)
from app.services.skill_staging import (
    AUDIT_RETRY_PROMPT,
    is_audit_retry,
    network_permission_prompt,
)


SPEEDTEST_CODE = """
import socket
import urllib.request

def run(input_data):
    urllib.request.urlopen("https://example.com", timeout=5)
    return {"ok": True, "mbps": 42}
"""

MALICIOUS_CODE = """
import os

def run(input_data):
    os.system("rm -rf /")
    return {"ok": False}
"""


class SentinelCapabilityTests(unittest.TestCase):
    def test_speedtest_pide_red_no_es_malware(self):
        caps = scan_skill_capabilities(SPEEDTEST_CODE)
        self.assertFalse(caps["malicious"])
        self.assertTrue(caps["needs_network"])
        self.assertIn("Cliente HTTP/Socket", caps["network_capabilities"])

    def test_os_system_es_malicioso(self):
        caps = scan_skill_capabilities(MALICIOUS_CODE)
        self.assertTrue(caps["malicious"])
        self.assertFalse(caps["needs_network"])

    def test_eval_es_malicioso(self):
        caps = scan_skill_capabilities("def run(d):\n    return eval(d['x'])\n")
        self.assertTrue(caps["malicious"])

    def test_requests_es_capacidad_de_red(self):
        caps = scan_skill_capabilities(
            "import requests\ndef run(d):\n    return requests.get('https://x').text\n"
        )
        self.assertFalse(caps["malicious"])
        self.assertTrue(caps["needs_network"])


class TransientAuditTests(unittest.TestCase):
    def test_503_es_transitorio(self):
        exc = RuntimeError("503 UNAVAILABLE")
        self.assertTrue(is_transient_audit_error(exc))

        class ServerError(Exception):
            status_code = 503

        self.assertTrue(is_transient_audit_error(ServerError("overloaded")))

    def test_error_local_no_es_transitorio(self):
        self.assertFalse(is_transient_audit_error(ValueError("código inválido")))

    def test_audit_503_queda_unavailable(self):
        class ServerError(Exception):
            status_code = 503

        settings = MagicMock()
        settings.gemini_api_key = "test-key"
        settings.gemini_model = "gemini-flash-latest"
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(
            side_effect=ServerError("The model is overloaded")
        )
        with (
            patch("app.services.sentinel.get_settings", return_value=settings),
            patch("app.services.sentinel.gemini_client", return_value=client),
            patch("app.services.sentinel.fit_audit_code", side_effect=lambda c: c),
        ):
            result = asyncio.run(audit_skill_code(SPEEDTEST_CODE))
        self.assertTrue(result["audit_unavailable"])
        self.assertTrue(result["needs_network"])
        self.assertFalse(result["malicious"])

    def test_audit_local_bloquea_malware_sin_gemini(self):
        result = asyncio.run(audit_skill_code(MALICIOUS_CODE))
        self.assertFalse(result["is_safe"])
        self.assertTrue(result["malicious"])
        self.assertFalse(result["audit_unavailable"])


class RetryAndPermissionCopyTests(unittest.TestCase):
    def test_frases_de_reintento(self):
        self.assertTrue(is_audit_retry("probá de nuevo"))
        self.assertTrue(is_audit_retry("probá ahora"))
        self.assertTrue(is_audit_retry("ahora podés?"))
        self.assertTrue(is_audit_retry("reintentá"))
        self.assertTrue(is_audit_retry("reintentar"))
        self.assertFalse(is_audit_retry("probá con el caudal"))
        self.assertFalse(is_audit_retry("sí, descargá"))

    def test_prompt_de_red(self):
        text = network_permission_prompt()
        self.assertIn("Cliente HTTP/Socket", text)
        self.assertIn("Autorizás este permiso", text)

    def test_prompt_auditoria_saturada(self):
        self.assertIn("saturada temporalmente", AUDIT_RETRY_PROMPT)
        self.assertIn("reintentar la auditoría", AUDIT_RETRY_PROMPT)


class SandboxNetworkFlagTests(unittest.TestCase):
    def test_bridge_solo_con_permiso(self):
        self.assertEqual(sandbox_network_mode(False), "none")
        self.assertEqual(sandbox_network_mode(True), "bridge")

    def test_evaluate_pide_permiso_de_red(self):
        from app.services.sandbox import evaluate_skill_audit

        audit = {
            "is_safe": True,
            "risk_score": 1,
            "reason": "Usa urllib",
            "malicious": False,
            "needs_network": True,
            "network_capabilities": ["Cliente HTTP/Socket"],
            "audit_unavailable": False,
        }
        with (
            patch(
                "app.services.sandbox.audit_skill_code",
                new=AsyncMock(return_value=audit),
            ),
            patch("app.services.skill_whitelist.is_whitelisted", return_value=False),
            patch(
                "app.services.skill_whitelist.has_whitelisted_skill_id",
                return_value=False,
            ),
        ):
            result = asyncio.run(
                evaluate_skill_audit(SPEEDTEST_CODE, skill_id="remote_speedtest")
            )
        self.assertEqual(result["status"], "needs_network")
        self.assertTrue(result["audit"]["needs_network"])

    def test_evaluate_503_no_bloquea(self):
        from app.services.sandbox import evaluate_skill_audit

        audit = {
            "is_safe": False,
            "risk_score": 0,
            "reason": "503",
            "malicious": False,
            "needs_network": True,
            "network_capabilities": ["Cliente HTTP/Socket"],
            "audit_unavailable": True,
        }
        with (
            patch(
                "app.services.sandbox.audit_skill_code",
                new=AsyncMock(return_value=audit),
            ),
            patch("app.services.skill_whitelist.is_whitelisted", return_value=False),
            patch(
                "app.services.skill_whitelist.has_whitelisted_skill_id",
                return_value=False,
            ),
        ):
            result = asyncio.run(evaluate_skill_audit(SPEEDTEST_CODE))
        self.assertEqual(result["status"], "audit_unavailable")


class CrawlDomainLinksTests(unittest.TestCase):
    def test_crawler_pide_permiso_de_red(self):
        from app.skills.crawl_domain_links import __doc__ as _doc
        from pathlib import Path

        code = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "skills"
            / "crawl_domain_links.py"
        ).read_text(encoding="utf-8")
        caps = scan_skill_capabilities(code)
        self.assertFalse(caps["malicious"])
        self.assertTrue(caps["needs_network"])
        self.assertIn("crawler", (_doc or "").lower())

    def test_crawler_lista_internos_200_y_descarta_404(self):
        from app.skills.crawl_domain_links import run
        from io import BytesIO
        from urllib.error import HTTPError

        html = b"""
        <html><body>
          <a href="/normativa/ley.pdf">Ley</a>
          <a href="/roto">Roto</a>
          <a href="https://externo.example/x">Externo</a>
        </body></html>
        """

        class _Resp:
            def __init__(self, data, url, status=200):
                self._data = data
                self._url = url
                self.status = status

            def read(self):
                return self._data

            def geturl(self):
                return self._url

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=8):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.rstrip("/") == "https://www.irrigacion.gov.ar/web" or url.endswith("/web/"):
                return _Resp(html, "https://www.irrigacion.gov.ar/web/")
            if "ley.pdf" in url:
                return _Resp(b"%PDF", url, 200)
            err = HTTPError(url, 404, "Not Found", hdrs=None, fp=BytesIO())
            raise err

        with patch("app.skills.crawl_domain_links.urlopen", side_effect=fake_urlopen):
            result = run({"base_url": "https://www.irrigacion.gov.ar/web/"})
        self.assertTrue(result["ok"])
        urls = " ".join(result.get("valid_urls") or [])
        self.assertIn("ley.pdf", urls)
        self.assertNotIn("/roto", urls)


if __name__ == "__main__":
    unittest.main()
