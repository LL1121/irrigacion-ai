"""CodeAct: observaciones del sandbox, tope de reintentos y ruteo del grafo."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

try:
    from app.services.sandbox import execute_python_script

    _HAS_SANDBOX = True
except ImportError:
    _HAS_SANDBOX = False

from app.services.codeact_observe import (
    codeact_execution_failed,
    codeact_retryable,
    format_codeact_observation,
)

try:
    from app.services.agent import (
        CODEACT_MAX_ATTEMPTS,
        SYSTEM_PROMPT_IRRIGACION,
        _local_catalog_plan,
        _route_after_plan,
        _run_codeact_node,
    )
    from app.services.skill_marketplace import APPROVAL_KIND_DOWNLOAD

    _HAS_AGENT = True
except ImportError:
    _HAS_AGENT = False


class CodeActSourceTests(unittest.TestCase):
    def test_agent_wires_codeact_without_pre_llm_interceptors(self):
        src = (
            Path(__file__).resolve().parents[1] / "app" / "services" / "agent.py"
        ).read_text(encoding="utf-8")
        self.assertIn("@tool\ndef execute_python_code", src)
        self.assertIn("CODEACT_MAX_ATTEMPTS = 3", src)
        self.assertIn("ESCRIBÍ EL CÓDIGO PYTHON NECESARIO", src)
        self.assertIn("run_codeact", src)
        self.assertNotIn("is_casual_chat", src)
        self.assertNotIn("ask_inputs_for_open_task", src)
        self.assertNotIn("Seguimos con lo de", src)


class CodeActObservationTests(unittest.TestCase):
    def test_success_observation_asks_to_answer_user(self):
        obs = format_codeact_observation(
            {
                "status": "executed",
                "execution": {"exit_code": 0, "stdout": "42 links", "stderr": ""},
            }
        )
        self.assertIn("TERMINÓ BIEN", obs)
        self.assertIn("42 links", obs)
        self.assertNotIn("FALLÓ", obs)

    def test_failure_observation_asks_to_fix(self):
        obs = format_codeact_observation(
            {
                "status": "executed",
                "execution": {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "SyntaxError: invalid syntax",
                    "error": "SyntaxError",
                },
            }
        )
        self.assertIn("FALLÓ", obs)
        self.assertIn("execute_python_code", obs)
        self.assertIn("SyntaxError", obs)

    def test_rejected_is_not_retryable(self):
        result = {"status": "rejected", "audit": {"reason": "os.system"}}
        self.assertTrue(codeact_execution_failed(result))
        self.assertFalse(codeact_retryable(result))

    def test_audit_unavailable_is_not_retryable(self):
        result = {"status": "audit_unavailable", "audit": {}}
        self.assertFalse(codeact_retryable(result))

    def test_runtime_error_is_retryable(self):
        result = {
            "status": "executed",
            "execution": {"exit_code": 1, "stderr": "404", "error": "HTTPError"},
        }
        self.assertTrue(codeact_retryable(result))


@unittest.skipUnless(_HAS_AGENT, "dependencias del agente no instaladas")
class CodeActRouteTests(unittest.TestCase):
    def test_pending_codeact_routes_to_run(self):
        from app.services.agent import _route_after_plan

        self.assertEqual(
            _route_after_plan(
                {"pending_codeact": {"code": "print(1)", "reason": "calc"}}
            ),
            "run_codeact",
        )

    def test_empty_codeact_does_not_run(self):
        from app.services.agent import _route_after_plan

        self.assertEqual(
            _route_after_plan({"pending_codeact": {"code": "  "}, "reply": "hola"}),
            "end_ok",
        )

    def test_max_attempts_is_three(self):
        from app.services.agent import CODEACT_MAX_ATTEMPTS

        self.assertEqual(CODEACT_MAX_ATTEMPTS, 3)

    def test_prompt_instructs_codeact(self):
        from app.services.agent import SYSTEM_PROMPT_IRRIGACION

        self.assertIn("execute_python_code", SYSTEM_PROMPT_IRRIGACION)
        self.assertIn("Sandbox seguro", SYSTEM_PROMPT_IRRIGACION)
        self.assertIn("ESCRIBÍ EL CÓDIGO PYTHON NECESARIO", SYSTEM_PROMPT_IRRIGACION)

    def test_plan_node_does_not_intercept_with_templates(self):
        from app.services import agent as agent_mod

        src = inspect.getsource(agent_mod._plan_node)
        self.assertNotIn("Seguimos con lo de", src)
        self.assertNotIn("ask_inputs_for_open_task", src)
        self.assertNotIn("is_casual_chat", src)
        self.assertNotIn("_force_skill_or_download", src)


@unittest.skipUnless(_HAS_SANDBOX, "dependencias de sandbox no instaladas")
class CodeActExecuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_inline_success(self):
        with (
            patch("app.services.sandbox.audit_skill_code", new_callable=AsyncMock) as audit,
            patch("app.services.sandbox._codeact_prefer_sandbox", return_value=False),
        ):
            audit.return_value = {
                "is_safe": True,
                "malicious": False,
                "needs_network": False,
                "audit_unavailable": False,
            }
            result = await execute_python_script("print('hola-codeact')")
        self.assertEqual(result["status"], "executed")
        self.assertIn("hola-codeact", result["execution"]["stdout"])
        self.assertEqual(result["execution"]["exit_code"], 0)

    async def test_malicious_rejected_without_running(self):
        result = await execute_python_script("import os\nos.system('ls')")
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(codeact_retryable(result))

    async def test_network_auto_granted_to_sandbox(self):
        with (
            patch("app.services.sandbox.audit_skill_code", new_callable=AsyncMock) as audit,
            patch("app.services.sandbox._write_codeact_workspace") as write,
            patch("app.services.sandbox._run_container") as run,
            patch("app.services.sandbox.shutil.rmtree"),
        ):
            audit.return_value = {
                "is_safe": True,
                "malicious": False,
                "needs_network": True,
                "audit_unavailable": False,
            }
            write.return_value = Path("/tmp/fake-codeact")
            run.return_value = {"exit_code": 0, "stdout": "ok", "stderr": ""}
            result = await execute_python_script(
                "import urllib.request\nprint('crawl')"
            )
            self.assertTrue(run.called)
            self.assertTrue(run.call_args.kwargs.get("allow_network"))
        self.assertEqual(result["status"], "executed")
        self.assertNotEqual(result.get("status"), "needs_network")


@unittest.skipUnless(_HAS_AGENT, "dependencias del agente no instaladas")
class CodeActNodeTests(unittest.TestCase):
    def test_run_node_increments_attempts_and_stops_at_cap(self):
        from app.services.agent import CODEACT_MAX_ATTEMPTS, _run_codeact_node

        fail = {
            "status": "executed",
            "execution": {
                "exit_code": 1,
                "stderr": "boom",
                "error": "boom",
                "stdout": "",
            },
        }
        with patch(
            "app.services.agent.execute_python_script_sync", return_value=fail
        ):
            out = _run_codeact_node(
                {
                    "pending_codeact": {"code": "print(1/0)", "reason": "x"},
                    "codeact_attempts": CODEACT_MAX_ATTEMPTS - 1,
                }
            )
        self.assertEqual(out["codeact_attempts"], CODEACT_MAX_ATTEMPTS)
        self.assertIsNone(out["pending_codeact"])
        self.assertIn("agotaron", out["codeact_observation"])

    def test_local_catalog_crawl_does_not_download_telemetry(self):
        from app.services.agent import _local_catalog_plan

        msg = (
            "escanear todos los subenlaces válidos del sitio "
            "https://www.irrigacion.gov.ar/web/"
        )
        plan = _local_catalog_plan(msg)
        self.assertIsNotNone(plan)
        skill = plan.get("pending_skill") or {}
        self.assertEqual(skill.get("id"), "crawl_domain_links")
        self.assertNotEqual(plan.get("approval_kind"), APPROVAL_KIND_DOWNLOAD)


if __name__ == "__main__":
    unittest.main()
