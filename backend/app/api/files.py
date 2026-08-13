"""Endpoints de carga, descarga y vista previa de archivos."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.auth_session import get_optional_user
from app.services.document_export import (
    artifact_info,
    artifact_preview,
    resolve_generated_document,
)
from app.services.ingest import SUPPORTED_EXTENSIONS, detect_file_type, ingest_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/documents/{file_id}")
def download_generated_document(file_id: str) -> FileResponse:
    path = resolve_generated_document(file_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Documento no encontrado o expirado.")
    info = artifact_info(file_id) or {}
    display_name = info.get("filename") or (
        path.name.split("_", 1)[-1] if "_" in path.name else path.name
    )
    media_type = info.get("mime") or "application/octet-stream"
    return FileResponse(
        path,
        media_type=str(media_type),
        filename=str(display_name),
    )


@router.get("/documents/{file_id}/info")
def generated_document_info(file_id: str) -> dict:
    info = artifact_info(file_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado o expirado.")
    return info


@router.get("/documents/{file_id}/preview")
def generated_document_preview(file_id: str) -> dict:
    preview = artifact_preview(file_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado o expirado.")
    return preview


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    scope: Literal["irrigacion", "personal"] = Form("irrigacion"),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Debés enviar al menos un archivo")

    user = get_optional_user(request, db)
    user_id = user["id"] if user else None
    if scope == "personal" and not user_id:
        raise HTTPException(
            status_code=401,
            detail="Para subir contexto personal necesitás iniciar sesión con Google.",
        )

    results: list[dict] = []
    for upload in files:
        filename = upload.filename or "untitled"
        try:
            detect_file_type(filename)
        except ValueError as exc:
            results.append(
                {
                    "filename": filename,
                    "chunks_created": 0,
                    "error": str(exc),
                }
            )
            continue

        try:
            content = await upload.read()
            if not content:
                results.append(
                    {
                        "filename": filename,
                        "chunks_created": 0,
                        "error": "Archivo vacío",
                    }
                )
                continue

            summary = ingest_file(
                db,
                content,
                filename,
                scope=scope,
                user_id=user_id if scope == "personal" else None,
            )
            results.append(summary)
        except Exception as exc:  # noqa: BLE001 - reportar error por archivo
            logger.exception("Error procesando %s", filename)
            db.rollback()
            results.append(
                {
                    "filename": filename,
                    "chunks_created": 0,
                    "error": str(exc),
                }
            )

    return {
        "processed": len(results),
        "results": results,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "scope": scope,
    }
