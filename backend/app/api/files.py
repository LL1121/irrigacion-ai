"""Endpoint de carga e indexación de archivos."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ingest import SUPPORTED_EXTENSIONS, detect_file_type, ingest_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Debés enviar al menos un archivo")

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

            summary = ingest_file(db, content, filename)
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
    }
