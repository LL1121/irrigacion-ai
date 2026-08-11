"""Orquestador de sandbox Docker efímero para skills auditadas."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import docker
from docker.errors import ContainerError, DockerException, ImageNotFound

from app.core.config import get_settings
from app.services.sentinel import audit_skill_code

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


def _run_container(work: Path) -> dict[str, Any]:
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
            network_mode="none",
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


async def execute_skill_in_sandbox(code_str: str, input_data: dict) -> dict[str, Any]:
    """
    Audita con Gemini y, si es segura, ejecuta la skill en un contenedor efímero.
    """
    audit = await audit_skill_code(code_str)
    if not audit.get("is_safe"):
        return {
            "status": "rejected",
            "audit": audit,
            "execution": None,
        }

    work: Path | None = None
    try:
        work = await asyncio.to_thread(_write_workspace, code_str, input_data or {})
        execution = await asyncio.to_thread(_run_container, work)
        return {
            "status": "executed",
            "audit": audit,
            "execution": execution,
        }
    finally:
        if work is not None and work.exists():
            shutil.rmtree(work, ignore_errors=True)
            logger.debug("Workspace temporal eliminado: %s", work)
