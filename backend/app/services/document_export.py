"""Persistencia y resolución de archivos generados por skills."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.config import get_settings

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
_FILE_ID = re.compile(r"^[0-9a-f-]{36}$")


def generated_documents_dir() -> Path:
    settings = get_settings()
    base = Path(settings.skill_workspace_dir) / "generated"
    base.mkdir(parents=True, exist_ok=True)
    return base


def sanitize_filename(name: str, default_ext: str = "") -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "archivo").strip()).strip("._")
    if not cleaned:
        cleaned = "archivo"
    if default_ext and not cleaned.lower().endswith(default_ext.lower()):
        cleaned = f"{cleaned}{default_ext}"
    return cleaned[:180]


def guess_mime(filename: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _meta_path(file_id: str) -> Path:
    return generated_documents_dir() / f"{file_id}.meta.json"


def _write_meta(file_id: str, meta: dict[str, Any]) -> None:
    _meta_path(file_id).write_text(
        json.dumps(meta, ensure_ascii=False),
        encoding="utf-8",
    )


def read_artifact_meta(file_id: str) -> dict[str, Any] | None:
    if not _FILE_ID.fullmatch(file_id or ""):
        return None
    path = _meta_path(file_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def save_artifact_from_base64(
    content_base64: str,
    filename: str,
    *,
    mime: str | None = None,
) -> tuple[str, Path]:
    """Persiste un archivo binario y devuelve (file_id, path)."""
    file_id = str(uuid.uuid4())
    safe_name = sanitize_filename(filename)
    dest = generated_documents_dir() / f"{file_id}_{safe_name}"
    raw = base64.b64decode(content_base64, validate=True)
    dest.write_bytes(raw)
    resolved_mime = guess_mime(safe_name, mime)
    _write_meta(
        file_id,
        {
            "file_id": file_id,
            "filename": safe_name,
            "mime": resolved_mime,
            "size_bytes": len(raw),
        },
    )
    return file_id, dest


def save_docx_from_base64(content_base64: str, filename: str) -> tuple[str, Path]:
    """Retrocompatible con skills Word."""
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"
    return save_artifact_from_base64(
        content_base64,
        filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def resolve_generated_document(file_id: str) -> Path | None:
    if not _FILE_ID.fullmatch(file_id or ""):
        return None
    folder = generated_documents_dir()
    matches = sorted(p for p in folder.glob(f"{file_id}_*") if p.is_file())
    return matches[0] if matches else None


def artifact_info(file_id: str) -> dict[str, Any] | None:
    path = resolve_generated_document(file_id)
    if path is None:
        return None
    meta = read_artifact_meta(file_id) or {}
    display_name = path.name.split("_", 1)[-1] if "_" in path.name else path.name
    mime = meta.get("mime") or guess_mime(display_name)
    size_bytes = meta.get("size_bytes") or path.stat().st_size
    previewable = mime.startswith("image/") or mime == "application/pdf" or mime.startswith(
        "text/"
    ) or mime in {
        "application/json",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return {
        "file_id": file_id,
        "filename": meta.get("filename") or display_name,
        "mime": mime,
        "size_bytes": size_bytes,
        "previewable": previewable,
    }


def extract_text_preview(path: Path, mime: str) -> str | None:
    if mime.startswith("text/") or mime in {"application/json", "text/csv"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:120_000]
        except OSError:
            return None
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            from docx import Document

            doc = Document(str(path))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(parts)[:120_000] if parts else "(Documento vacío)"
        except Exception:
            return None
    return None


def artifact_preview(file_id: str) -> dict[str, Any] | None:
    info = artifact_info(file_id)
    path = resolve_generated_document(file_id)
    if info is None or path is None:
        return None
    mime = str(info["mime"])
    if mime.startswith("image/") or mime == "application/pdf":
        return {"mode": "binary", **info}
    text = extract_text_preview(path, mime)
    if text is not None:
        return {"mode": "text", "content": text, **info}
    return {"mode": "unsupported", **info}
