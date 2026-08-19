"""Orquestador de sandbox Docker efímero para skills auditadas."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.codeact_observe import (
    codeact_execution_failed,
    codeact_retryable,
    format_codeact_observation,
)
from app.services.sentinel import audit_skill_code, scan_skill_capabilities

logger = logging.getLogger(__name__)

RUNNER_TEMPLATE = '''\
import json
import traceback
from pathlib import Path

def _load_input():
    return json.loads(Path("/skill/input.json").read_text(encoding="utf-8"))

input_data = _load_input()
result = None

try:
{indented_skill}

    if callable(globals().get("run")):
        result = run(input_data)  # noqa: F821
    elif "result" in globals() and result is not None:
        pass
    else:
        result = {{"ok": True, "note": "Skill ejecutada sin variable result/run"}}

    print(json.dumps({{"success": True, "result": result}}, ensure_ascii=False, default=str))
except Exception as exc:
    print(json.dumps({{
        "success": False,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }}, ensure_ascii=False))
'''


def _indent_skill(code_str: str) -> str:
    lines = code_str.replace("\r\n", "\n").split("\n")
    return "\n".join(("    " + line) if line.strip() else "" for line in lines)


def _write_workspace(code_str: str, input_data: dict) -> Path:
    settings = get_settings()
    base = Path(settings.skill_workspace_dir)
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="irrigacion_skill_", dir=str(base)))
    # Permisos legibles para el contenedor efímero
    work.chmod(0o755)
    runner = RUNNER_TEMPLATE.format(indented_skill=_indent_skill(code_str))
    runner_path = work / "runner.py"
    input_path = work / "input.json"
    runner_path.write_text(runner, encoding="utf-8")
    input_path.write_text(
        json.dumps(input_data, ensure_ascii=False),
        encoding="utf-8",
    )
    runner_path.chmod(0o644)
    input_path.chmod(0o644)
    return work


CODEACT_TEMPLATE = '''\
import traceback
import sys

try:
{indented_code}
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''


def sandbox_network_mode(allow_network: bool) -> str:
    """Salida a internet solo si el usuario autorizó el permiso de red."""
    return "bridge" if allow_network else "none"


def _run_container(work: Path, *, allow_network: bool = False) -> dict[str, Any]:
    import docker
    from docker.errors import ContainerError, DockerException, ImageNotFound

    settings = get_settings()
    client = docker.from_env()
    image = settings.skill_sandbox_image

    try:
        client.images.get(image)
    except ImageNotFound as exc:
        raise RuntimeError(
            f"Imagen '{image}' no encontrada. Ejecutá: "
            "python backend/sandbox_env/build_image.py"
        ) from exc

    try:
        # Código e input en /skill (ro). /tmp queda como tmpfs escribible aislado.
        output = client.containers.run(
            image=image,
            command=["python", "/skill/runner.py"],
            volumes={
                str(work): {
                    "bind": "/skill",
                    "mode": "ro",
                },
            },
            network_mode=sandbox_network_mode(allow_network),
            mem_limit="256m",
            nano_cpus=500_000_000,
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            remove=True,
            stdout=True,
            stderr=True,
        )
    except ContainerError as exc:
        raw_out = exc.container.logs(stdout=True, stderr=False) if getattr(exc, "container", None) else b""
        raw_err = exc.stderr if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr or "").encode()
        stdout = raw_out.decode("utf-8", errors="replace") if isinstance(raw_out, (bytes, bytearray)) else str(raw_out or "")
        stderr = raw_err.decode("utf-8", errors="replace") if isinstance(raw_err, (bytes, bytearray)) else str(raw_err or "")
        if not stderr:
            stderr = str(exc)
        return {
            "executed": True,
            "exit_code": exc.exit_status,
            "stdout": stdout,
            "stderr": stderr,
            "parsed": _try_parse_json(stdout),
            "error": f"ContainerError: {exc}",
        }
    except DockerException as exc:
        raise RuntimeError(f"Error del daemon Docker: {exc}") from exc

    if isinstance(output, bytes):
        stdout = output.decode("utf-8", errors="replace")
        stderr = ""
    elif isinstance(output, tuple):
        out_b, err_b = output
        stdout = (out_b or b"").decode("utf-8", errors="replace")
        stderr = (err_b or b"").decode("utf-8", errors="replace")
    else:
        stdout = str(output)
        stderr = ""

    return {
        "executed": True,
        "exit_code": 0,
        "stdout": stdout,
        "stderr": stderr,
        "parsed": _try_parse_json(stdout),
    }


def _try_parse_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    # Tomar la última línea JSON válida (por si hay prints previos)
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _run_inline(code_str: str, input_data: dict) -> dict[str, Any]:
    """Ejecuta la skill en el mismo proceso del API (sin contenedor)."""
    import traceback

    from app.services.skill_http import build_fetch_url, extract_urls

    extra_urls = extract_urls(json.dumps(input_data or {}, ensure_ascii=False))
    for key in ("url", "urls", "query", "pedido"):
        val = (input_data or {}).get(key)
        if isinstance(val, str):
            extra_urls.extend(extract_urls(val))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    extra_urls.extend(extract_urls(item))

    namespace: dict[str, Any] = {
        "__name__": "__skill__",
        "fetch_url": build_fetch_url(extra_allowed_urls=extra_urls),
    }
    try:
        exec(compile(code_str, "<skill>", "exec"), namespace)  # noqa: S102
        run_fn = namespace.get("run")
        if not callable(run_fn):
            err = "Skill sin función run(input_data)"
            payload = {"success": False, "error": err}
            return {
                "executed": True,
                "exit_code": 1,
                "stdout": json.dumps(payload, ensure_ascii=False),
                "stderr": err,
                "parsed": payload,
                "error": err,
                "mode": "inline",
            }
        result = run_fn(input_data or {})
        payload = {"success": True, "result": result}
        return {
            "executed": True,
            "exit_code": 0,
            "stdout": json.dumps(payload, ensure_ascii=False, default=str),
            "stderr": "",
            "parsed": payload,
            "mode": "inline",
        }
    except Exception as exc:
        payload = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        return {
            "executed": True,
            "exit_code": 1,
            "stdout": json.dumps(payload, ensure_ascii=False),
            "stderr": str(exc),
            "parsed": payload,
            "error": str(exc),
            "mode": "inline",
        }


def _run_async(factory):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


def _write_codeact_workspace(code_str: str) -> Path:
    settings = get_settings()
    base = Path(settings.skill_workspace_dir)
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="irrigacion_codeact_", dir=str(base)))
    work.chmod(0o755)
    runner = CODEACT_TEMPLATE.replace("{indented_code}", _indent_skill(code_str))
    runner_path = work / "runner.py"
    runner_path.write_text(runner, encoding="utf-8")
    runner_path.chmod(0o644)
    return work


def _run_inline_script(code_str: str) -> dict[str, Any]:
    """Ejecuta un script Python en el proceso API (modo inline)."""
    import contextlib
    import io
    import traceback

    from app.services.skill_http import build_fetch_url

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    namespace: dict[str, Any] = {
        "__name__": "__main__",
        "fetch_url": build_fetch_url(extra_allowed_urls=[]),
    }
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(compile(code_str, "<codeact>", "exec"), namespace)  # noqa: S102
        return {
            "executed": True,
            "exit_code": 0,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "error": None,
            "mode": "inline",
        }
    except Exception as exc:
        stderr_buf.write(traceback.format_exc())
        return {
            "executed": True,
            "exit_code": 1,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "error": str(exc),
            "mode": "inline",
        }


_CODEACT_SANDBOX_HINTS = (
    "pandas",
    "numpy",
    "bs4",
    "beautifulsoup",
    "lxml",
    "openpyxl",
    "httpx",
    "docx",
    "requests",
    "urllib",
)


def _codeact_prefer_sandbox(code_str: str, needs_network: bool) -> bool:
    settings = get_settings()
    mode = (settings.skill_execution_mode or "inline").strip().lower()
    if mode == "sandbox":
        return True
    if needs_network:
        return True
    lowered = (code_str or "").lower()
    return any(hint in lowered for hint in _CODEACT_SANDBOX_HINTS)


async def execute_python_script(code_str: str) -> dict[str, Any]:
    """Audita un snippet CodeAct y lo corre en sandbox (o inline si no hay imagen).

    A diferencia de execute_skill: no hay HITL de red ni whitelist. Si Gemini
    marca el código como seguro y usa red, el contenedor sale con --network bridge.
    """
    source = (code_str or "").strip()
    caps = scan_skill_capabilities(source)
    if caps.get("malicious"):
        audit = {
            "is_safe": False,
            "risk_score": 10,
            "reason": "Bloqueo local (centinela): "
            + "; ".join(caps.get("malice_findings") or ["código inseguro"]),
            "malicious": True,
            "needs_network": False,
            "network_capabilities": [],
            "audit_unavailable": False,
        }
        return {"status": "rejected", "audit": audit, "execution": None}

    audit = await audit_skill_code(source)
    if audit.get("audit_unavailable"):
        return {"status": "audit_unavailable", "audit": audit, "execution": None}
    if audit.get("malicious") or not audit.get("is_safe"):
        return {"status": "rejected", "audit": audit, "execution": None}

    needs_net = bool(audit.get("needs_network") or caps.get("needs_network"))
    allow_network = bool(needs_net)
    use_sandbox = _codeact_prefer_sandbox(source, needs_net)

    if use_sandbox:
        work: Path | None = None
        try:
            work = await asyncio.to_thread(_write_codeact_workspace, source)
            execution = await asyncio.to_thread(
                _run_container, work, allow_network=allow_network
            )
            if isinstance(execution, dict):
                execution = {**execution, "mode": "sandbox"}
            return {
                "status": "executed",
                "audit": audit,
                "execution": execution,
            }
        except RuntimeError as exc:
            logger.warning("Sandbox CodeAct no disponible, caigo a inline: %s", exc)
        finally:
            if work is not None and work.exists():
                shutil.rmtree(work, ignore_errors=True)

    execution = await asyncio.to_thread(_run_inline_script, source)
    return {
        "status": "executed",
        "audit": audit,
        "execution": execution,
    }


def execute_python_script_sync(code_str: str) -> dict[str, Any]:
    return _run_async(lambda: execute_python_script(code_str))


def execute_skill_sync(
    code_str: str,
    input_data: dict,
    *,
    skill_id: str | None = None,
    skill_name: str | None = None,
    source: str | None = None,
    allow_network: bool = False,
) -> dict[str, Any]:
    """Wrapper síncrono para nodos LangGraph (el endpoint de chat corre en threadpool)."""

    return _run_async(
        lambda: execute_skill(
            code_str,
            input_data,
            skill_id=skill_id,
            skill_name=skill_name,
            source=source,
            allow_network=allow_network,
        )
    )


def evaluate_skill_audit_sync(
    code_str: str,
    *,
    skill_id: str | None = None,
    skill_name: str | None = None,
    source: str | None = None,
    allow_network: bool = False,
) -> dict[str, Any]:
    return _run_async(
        lambda: evaluate_skill_audit(
            code_str,
            skill_id=skill_id,
            skill_name=skill_name,
            source=source,
            allow_network=allow_network,
        )
    )


# Alias histórico
execute_skill_in_sandbox_sync = execute_skill_sync


async def evaluate_skill_audit(
    code_str: str,
    *,
    skill_id: str | None = None,
    skill_name: str | None = None,
    source: str | None = None,
    allow_network: bool = False,
) -> dict[str, Any]:
    """
    Audita sin ejecutar.

    status: ok | rejected | audit_unavailable | needs_network
    """
    from app.services.skill_whitelist import (
        add_to_whitelist,
        has_whitelisted_skill_id,
        is_whitelisted,
        whitelist_allows_network,
    )

    caps = scan_skill_capabilities(code_str or "")
    curated_ids = {"remote_telemetria_punto"}
    if skill_id and is_whitelisted(skill_id, code_str):
        audit: dict[str, Any] = {
            "is_safe": True,
            "risk_score": 0,
            "reason": "Whitelist: skill previamente auditada por Gemini",
            "whitelisted": True,
            "malicious": False,
            "needs_network": bool(caps.get("needs_network")),
            "network_capabilities": list(caps.get("network_capabilities") or []),
            "audit_unavailable": False,
        }
        if caps.get("needs_network") and whitelist_allows_network(skill_id, code_str):
            allow_network = True
    elif skill_id and skill_id in curated_ids and has_whitelisted_skill_id(skill_id):
        audit = {
            "is_safe": True,
            "risk_score": 0,
            "reason": "Whitelist: skill curada previamente auditada",
            "whitelisted": True,
            "malicious": False,
            "needs_network": bool(caps.get("needs_network")),
            "network_capabilities": list(caps.get("network_capabilities") or []),
            "audit_unavailable": False,
        }
        add_to_whitelist(
            skill_id=skill_id,
            code_str=code_str,
            skill_name=skill_name,
            source=source or "remote",
            audit=audit,
        )
    else:
        audit = await audit_skill_code(code_str)

    if caps.get("malicious") or audit.get("malicious"):
        return {"status": "rejected", "audit": audit, "allow_network": False}

    if audit.get("audit_unavailable"):
        return {
            "status": "audit_unavailable",
            "audit": audit,
            "allow_network": False,
        }

    if not audit.get("is_safe"):
        return {"status": "rejected", "audit": audit, "allow_network": False}

    needs_net = bool(audit.get("needs_network") or caps.get("needs_network"))
    if needs_net and not allow_network:
        return {
            "status": "needs_network",
            "audit": {
                **audit,
                "needs_network": True,
                "network_capabilities": list(
                    audit.get("network_capabilities")
                    or caps.get("network_capabilities")
                    or ["Cliente HTTP/Socket"]
                ),
            },
            "allow_network": False,
        }

    if skill_id and not audit.get("whitelisted"):
        add_to_whitelist(
            skill_id=skill_id,
            code_str=code_str,
            skill_name=skill_name,
            source=source,
            audit=audit,
            network_granted=bool(allow_network and needs_net),
        )
    elif skill_id and allow_network and needs_net:
        add_to_whitelist(
            skill_id=skill_id,
            code_str=code_str,
            skill_name=skill_name,
            source=source,
            audit=audit,
            network_granted=True,
        )

    return {"status": "ok", "audit": audit, "allow_network": bool(allow_network)}


async def execute_skill(
    code_str: str,
    input_data: dict,
    *,
    skill_id: str | None = None,
    skill_name: str | None = None,
    source: str | None = None,
    allow_network: bool = False,
) -> dict[str, Any]:
    """
    Audita con Gemini (o salta si está en whitelist) y ejecuta la skill.
    Modo controlado por SKILL_EXECUTION_MODE: inline | sandbox.
    Con allow_network el contenedor usa --network bridge.
    """
    prepared = await evaluate_skill_audit(
        code_str,
        skill_id=skill_id,
        skill_name=skill_name,
        source=source,
        allow_network=allow_network,
    )
    audit = prepared.get("audit") or {}
    status = prepared.get("status") or "rejected"
    if status != "ok":
        return {
            "status": status,
            "audit": audit,
            "execution": None,
        }

    allow_network = bool(prepared.get("allow_network") or allow_network)
    settings = get_settings()
    mode = (settings.skill_execution_mode or "inline").strip().lower()
    if mode not in {"inline", "sandbox"}:
        mode = "inline"
    # fetch_url solo existe inyectada en inline.
    if "fetch_url" in (code_str or ""):
        mode = "inline"

    if mode == "inline":
        execution = await asyncio.to_thread(_run_inline, code_str, input_data or {})
        return {
            "status": "executed",
            "audit": audit,
            "execution": execution,
        }

    work: Path | None = None
    try:
        work = await asyncio.to_thread(_write_workspace, code_str, input_data or {})
        execution = await asyncio.to_thread(
            _run_container, work, allow_network=allow_network
        )
        if isinstance(execution, dict):
            execution = {**execution, "mode": "sandbox"}
        return {
            "status": "executed",
            "audit": audit,
            "execution": execution,
        }
    finally:
        if work is not None and work.exists():
            shutil.rmtree(work, ignore_errors=True)
            logger.debug("Workspace temporal eliminado: %s", work)


async def execute_skill_in_sandbox(code_str: str, input_data: dict) -> dict[str, Any]:
    """Compat: misma entrada que execute_skill (respeta SKILL_EXECUTION_MODE)."""
    return await execute_skill(code_str, input_data)
