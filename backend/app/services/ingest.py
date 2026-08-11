"""Ingestión de documentos: extracción de texto, chunking, embeddings y persistencia."""

from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path

import pymupdf as fitz
from docx import Document
from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}

OCR_SYSTEM_PROMPT = (
    "Eres un motor OCR estricto. Transcribe TODO el texto visible en la imagen "
    "a Markdown. Respeta tablas (usa sintaxis Markdown de tablas), encabezados, "
    "listas y datos numéricos. No inventes contenido. No agregues comentarios "
    "ni explicaciones: solo el texto transcripto."
)


def _openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Tipo de archivo no soportado: '{ext}'. "
            f"Permitidos: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return ext


def split_text(text_content: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    settings = get_settings()
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    cleaned = text_content.strip()
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    text_len = len(cleaned)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(0, end - overlap)

    return chunks


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    settings = get_settings()
    client = _openai_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    # Mantener orden por index
    sorted_data = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in sorted_data]


def _ocr_image_bytes(image_bytes: bytes, mime: str = "image/png") -> str:
    settings = get_settings()
    client = _openai_client()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    response = client.chat.completions.create(
        model=settings.ocr_model,
        messages=[
            {"role": "system", "content": OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe esta imagen a Markdown.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            },
        ],
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()


def _extract_text_from_pdf(path: Path) -> str:
    settings = get_settings()
    doc = fitz.open(path)
    try:
        native_parts: list[str] = []
        for page in doc:
            native_parts.append(page.get_text("text") or "")

        native_text = "\n".join(native_parts).strip()
        if len(native_text) >= settings.scanned_pdf_char_threshold:
            return native_text

        logger.info(
            "PDF escaneado o con poco texto (%s chars). Usando OCR con %s.",
            len(native_text),
            settings.ocr_model,
        )
        ocr_parts: list[str] = []
        for page_index, page in enumerate(doc):
            # Render a ~150 DPI para balance calidad/tamaño
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image_bytes = pix.tobytes("png")
            page_text = _ocr_image_bytes(image_bytes, mime="image/png")
            if page_text:
                ocr_parts.append(f"## Página {page_index + 1}\n\n{page_text}")
        return "\n\n".join(ocr_parts).strip()
    finally:
        doc.close()


def _extract_text_from_docx(path: Path) -> str:
    document = Document(path)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]

    # Incluir texto de tablas
    table_blocks: list[str] = []
    for table in document.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append("| " + " | ".join(cells) + " |")
        if rows:
            table_blocks.append("\n".join(rows))

    parts = paragraphs + table_blocks
    return "\n\n".join(parts).strip()


def _extract_text_from_image(path: Path) -> str:
    ext = path.suffix.lower()
    mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
    image_bytes = path.read_bytes()
    return _ocr_image_bytes(image_bytes, mime=mime)


def extract_text(path: Path, filename: str) -> str:
    ext = detect_file_type(filename)
    if ext == ".pdf":
        return _extract_text_from_pdf(path)
    if ext == ".docx":
        return _extract_text_from_docx(path)
    if ext in {".png", ".jpg", ".jpeg"}:
        return _extract_text_from_image(path)
    raise ValueError(f"Extensión no manejada: {ext}")


def persist_chunks(
    db: Session,
    document_name: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    if len(chunks) != len(embeddings):
        raise ValueError("La cantidad de chunks y embeddings no coincide")

    insert_sql = text(
        """
        INSERT INTO document_chunks (document_name, content, embedding)
        VALUES (:document_name, :content, CAST(:embedding AS vector))
        """
    )

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        embedding_literal = "[" + ",".join(str(float(v)) for v in embedding) + "]"
        db.execute(
            insert_sql,
            {
                "document_name": document_name,
                "content": chunk,
                "embedding": embedding_literal,
            },
        )
    db.commit()
    return len(chunks)


def ingest_file(db: Session, file_bytes: bytes, filename: str) -> dict:
    """Procesa un archivo subido y lo indexa en document_chunks."""
    detect_file_type(filename)
    suffix = Path(filename).suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        tmp_path = Path(tmp.name)

        extracted = extract_text(tmp_path, filename)
        if not extracted.strip():
            return {
                "filename": filename,
                "chunks_created": 0,
                "warning": "No se pudo extraer texto del archivo",
            }

        chunks = split_text(extracted)
        if not chunks:
            return {
                "filename": filename,
                "chunks_created": 0,
                "warning": "El texto extraído no produjo chunks",
            }

        embeddings = generate_embeddings(chunks)
        created = persist_chunks(db, filename, chunks, embeddings)

        return {
            "filename": filename,
            "chunks_created": created,
        }
