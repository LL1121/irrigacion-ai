"""Punto de entrada FastAPI — irrigacion-bot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import chat, files, skills
from app.core.checkpointer import close_checkpointer, init_checkpointer
from app.core.config import get_settings
from app.core.database import ensure_runtime_schema

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.is_production:
        settings.assert_production_ready()
    ensure_runtime_schema()
    init_checkpointer()
    yield
    close_checkpointer()


app = FastAPI(
    title="irrigacion-bot",
    description=(
        "API institucional de Irrigación de Malargüe "
        "(ingesta + caché + LangGraph + skills en sandbox)"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANTE: las rutas de la API se registran ANTES de montar los archivos
# estáticos de la PWA (ver más abajo). Starlette resuelve rutas en el orden
# en que se agregan, así que /api/*, /health, etc. siempre tienen prioridad
# sobre el catch-all "/" del SPA.
app.include_router(files.router)
app.include_router(chat.router)
app.include_router(skills.router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "irrigacion-bot",
        "env": settings.app_env,
    }


def _resolve_frontend_dist() -> Path | None:
    """Ubica el build de la PWA (desktop-app/dist) para servirlo como SPA.

    Soporta tanto el layout de monorepo (backend/ y desktop-app/ como
    hermanos) como un override explícito vía FRONTEND_DIST_DIR (útil en
    Docker, donde el build se monta como volumen dentro del contenedor).
    """
    candidates: list[Path] = []
    override = _settings.frontend_dist_dir.strip()
    if override:
        candidates.append(Path(override))

    backend_dir = Path(__file__).resolve().parent
    candidates.append(backend_dir.parent / "desktop-app" / "dist")
    candidates.append(backend_dir / "desktop-app" / "dist")
    candidates.append(Path.cwd() / "desktop-app" / "dist")

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


_frontend_dist = _resolve_frontend_dist()
if _frontend_dist is not None:
    logger.info("Sirviendo la PWA compilada desde %s", _frontend_dist)
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="pwa")
else:
    logger.warning(
        "No se encontró desktop-app/dist; la SPA no se servirá en '/'. "
        "Ejecutá 'npm run build' en desktop-app/ (o definí FRONTEND_DIST_DIR) "
        "para habilitarla."
    )
