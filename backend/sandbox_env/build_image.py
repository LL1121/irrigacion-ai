#!/usr/bin/env python3
"""Construye la imagen base skill-sandbox-image (una sola vez)."""

from __future__ import annotations

import sys
from pathlib import Path

import docker

IMAGE_TAG = "skill-sandbox-image"
DOCKERFILE_DIR = Path(__file__).resolve().parent


def main() -> int:
    client = docker.from_env()
    print(f"Construyendo {IMAGE_TAG} desde {DOCKERFILE_DIR} …")
    image, logs = client.images.build(
        path=str(DOCKERFILE_DIR),
        tag=IMAGE_TAG,
        rm=True,
        forcerm=True,
    )
    for entry in logs:
        if isinstance(entry, dict) and "stream" in entry:
            print(entry["stream"], end="")
    print(f"Listo: {image.tags or [image.short_id]}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except docker.errors.DockerException as exc:
        print(f"Error de Docker: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
