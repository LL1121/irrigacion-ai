#!/usr/bin/env python3
"""Ingesta masiva de documentación oficial de Irrigación → PostgreSQL (RAG)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal, ensure_runtime_schema
from app.services.official_ingest import (
    DEFAULT_CATEGORY,
    ingest_official_file_record,
    ingest_official_json_manifest,
    ingest_official_url_record,
)


def _progress_bar(done: int, total: int) -> None:
    try:
        from tqdm import tqdm

        if not hasattr(_progress_bar, "_bar"):
            _progress_bar._bar = tqdm(total=total, unit="chunk", desc="Embeddings")
        _progress_bar._bar.n = done
        _progress_bar._bar.refresh()
        if done >= total:
            _progress_bar._bar.close()
            delattr(_progress_bar, "_bar")
    except ImportError:
        pct = (100 * done // total) if total else 100
        print(f"\rEmbeddings: {done}/{total} ({pct}%)", end="", flush=True)
        if done >= total:
            print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Indexa documentos oficiales de Irrigación en document_chunks."
    )
    parser.add_argument("--url", help="URL directa (HTML o PDF)")
    parser.add_argument("--file", type=Path, help="Archivo local .pdf, .docx o .txt")
    parser.add_argument("--json", type=Path, dest="manifest", help="JSON con lista de URLs")
    parser.add_argument("--title", help="Título del documento (obligatorio con --url/--file)")
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Categoría de metadatos (default: normativa)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Fragmentos por lote de embeddings (default: 8)",
    )
    args = parser.parse_args()

    if not any([args.url, args.file, args.manifest]):
        parser.error("Indicá --url, --file o --json")

    ensure_runtime_schema()
    db = SessionLocal()
    try:
        if args.manifest:
            print(f"Manifest: {args.manifest}")
            results = ingest_official_json_manifest(
                db,
                args.manifest.resolve(),
                batch_size=args.batch_size,
                on_progress=_progress_bar,
            )
            total_chunks = sum(int(r.get("chunks_created") or 0) for r in results)
            print(f"OK: {len(results)} documento(s), {total_chunks} fragmento(s).")
            return 0

        if args.url:
            if not args.title:
                parser.error("--title es obligatorio con --url")
            print(f"URL: {args.url}")
            result = ingest_official_url_record(
                db,
                url=args.url.strip(),
                title=args.title.strip(),
                category=args.category,
                batch_size=args.batch_size,
                on_progress=_progress_bar,
            )
        else:
            path = args.file.resolve()
            title = (args.title or path.stem).strip()
            print(f"Archivo: {path}")
            result = ingest_official_file_record(
                db,
                path=path,
                title=title,
                category=args.category,
                batch_size=args.batch_size,
                on_progress=_progress_bar,
            )

        print(
            f"OK: «{result.get('title')}» → {result.get('chunks_created')} fragmento(s) "
            f"({result.get('document_name')})"
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
