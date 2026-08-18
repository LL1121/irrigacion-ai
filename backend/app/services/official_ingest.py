"""Ingesta de documentos oficiales: web, PDF, DOCX, TXT → RAG."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.ingest import (
    generate_embeddings,
    persist_chunks,
    split_text,
    _extract_text_from_docx,
)

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = "normativa"
DEFAULT_SCOPE = "irrigacion"
DEFAULT_SOURCE = "oficial"
USER_AGENT = (
    "irrigacion-bot/1.0 (+https://github.com/LL1121/irrigacion-ai; "
    "ingesta documental institucional)"
)

_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"}


def _slug(value: str, *, max_len: int = 80) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "documento").strip().lower())
    base = re.sub(r"-+", "-", base).strip("-") or "documento"
    return base[:max_len]


def document_name_for_official(title: str, *, category: str = DEFAULT_CATEGORY) -> str:
    return f"oficial:{category}:{_slug(title)}"


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    for selector in (
        "[role='navigation']",
        "[role='banner']",
        "[role='contentinfo']",
        ".navbar",
        ".nav",
        ".footer",
        ".cookie",
        ".banner",
    ):
        for node in soup.select(selector):
            node.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines).strip()


def fetch_url_text(url: str, *, timeout: float = 45.0) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("La URL debe ser http o https")
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.get(url.strip())
        response.raise_for_status()
    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return extract_pdf_bytes(response.content)
    if "html" in content_type or "text/plain" in content_type or "<" in response.text[:200]:
        if "html" in content_type or "<html" in response.text[:500].lower():
            return clean_html(response.text)
        return response.text.strip()
    return response.text.strip()


def extract_pdf_bytes(data: bytes) -> str:
    """PDF oficial: pdfplumber → pypdf → texto vacío."""
    import io

    text_parts: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text.strip())
    except Exception:
        logger.debug("pdfplumber no extrajo texto; probando pypdf", exc_info=True)
        text_parts = []

    if not text_parts:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text.strip())
        except Exception as exc:
            raise RuntimeError(f"No se pudo extraer texto del PDF: {exc}") from exc

    joined = "\n\n".join(text_parts).strip()
    if not joined:
        raise RuntimeError("El PDF no contiene texto extraíble")
    return joined


def extract_local_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_bytes(path.read_bytes())
    if ext == ".docx":
        return _extract_text_from_docx(path)
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="replace").strip()
    raise ValueError(f"Extensión no soportada para ingesta oficial: {ext}")


def _delete_existing_official(
    db: Session,
    *,
    document_name: str,
    url: str | None = None,
) -> int:
    if url:
        row = db.execute(
            text(
                """
                DELETE FROM document_chunks
                WHERE scope = 'irrigacion'
                  AND source = :source
                  AND (
                        document_name = :document_name
                        OR metadata->>'url' = :url
                  )
                """
            ),
            {
                "document_name": document_name,
                "url": url,
                "source": DEFAULT_SOURCE,
            },
        )
    else:
        row = db.execute(
            text(
                """
                DELETE FROM document_chunks
                WHERE scope = 'irrigacion'
                  AND document_name = :document_name
                  AND source = :source
                """
            ),
            {"document_name": document_name, "source": DEFAULT_SOURCE},
        )
    db.commit()
    return int(getattr(row, "rowcount", 0) or 0)


def generate_embeddings_batched(
    texts: list[str],
    *,
    batch_size: int = 8,
    pause_seconds: float = 0.25,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    vectors: list[list[float]] = []
    total = len(texts)
    for start in range(0, total, batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(generate_embeddings(batch))
        done = min(start + len(batch), total)
        if on_progress:
            on_progress(done, total)
        if start + batch_size < total and pause_seconds > 0:
            time.sleep(pause_seconds)
    return vectors


def ingest_official_text(
    db: Session,
    *,
    text_content: str,
    title: str,
    url: str | None = None,
    category: str = DEFAULT_CATEGORY,
    replace_existing: bool = True,
    batch_size: int = 8,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    cleaned = (text_content or "").strip()
    if not cleaned:
        raise ValueError("No hay texto para indexar")

    doc_name = document_name_for_official(title, category=category)
    metadata = {
        "source": DEFAULT_SOURCE,
        "title": title,
        "url": url or "",
        "category": category,
    }

    if replace_existing:
        _delete_existing_official(db, document_name=doc_name, url=url)

    chunks = split_text(cleaned)
    if not chunks:
        chunks = [cleaned]

    embeddings = generate_embeddings_batched(
        chunks,
        batch_size=batch_size,
        on_progress=on_progress,
    )
    created = persist_chunks(
        db,
        doc_name,
        chunks,
        embeddings,
        scope=DEFAULT_SCOPE,
        user_id=None,
        source=DEFAULT_SOURCE,
        title=title,
        metadata=metadata,
    )
    return {
        "document_name": doc_name,
        "title": title,
        "url": url,
        "category": category,
        "chunks_created": created,
        "metadata": metadata,
    }


def ingest_official_url_record(
    db: Session,
    *,
    url: str,
    title: str,
    category: str = DEFAULT_CATEGORY,
    batch_size: int = 8,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    body = fetch_url_text(url)
    return ingest_official_text(
        db,
        text_content=body,
        title=title,
        url=url,
        category=category,
        batch_size=batch_size,
        on_progress=on_progress,
    )


def ingest_official_file_record(
    db: Session,
    *,
    path: Path,
    title: str | None = None,
    category: str = DEFAULT_CATEGORY,
    batch_size: int = 8,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    label = title or path.stem.replace("_", " ").strip() or path.name
    body = extract_local_file(path)
    return ingest_official_text(
        db,
        text_content=body,
        title=label,
        url=str(path),
        category=category,
        batch_size=batch_size,
        on_progress=on_progress,
    )


def ingest_official_json_manifest(
    db: Session,
    manifest_path: Path,
    *,
    batch_size: int = 8,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]]
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict) and isinstance(raw.get("documents"), list):
        entries = raw["documents"]
    else:
        raise ValueError("El JSON debe ser una lista o {documents: [...]}")

    results: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or item.get("name") or url or "Documento").strip()
        category = str(item.get("category") or DEFAULT_CATEGORY).strip()
        if not url:
            continue
        results.append(
            ingest_official_url_record(
                db,
                url=url,
                title=title,
                category=category,
                batch_size=batch_size,
                on_progress=on_progress,
            )
        )
    return results
