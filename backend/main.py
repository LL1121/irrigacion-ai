"""Punto de entrada FastAPI — irrigacion-bot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chat, files, legal, skills
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
app.include_router(auth.router)
app.include_router(legal.router)

_OAUTH_HOME_HTML = Path(__file__).resolve().parent / "app" / "static" / "oauth_home.html"
_OAUTH_HOME_CSS = Path(__file__).resolve().parent / "app" / "static" / "oauth_home.css"


@app.get("/", include_in_schema=False)
def oauth_public_homepage() -> FileResponse:
    """HTML estático (sin JS) para la verificación OAuth de Google."""
    return FileResponse(
        _OAUTH_HOME_HTML,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/oauth-home.css", include_in_schema=False)
def oauth_public_homepage_css() -> FileResponse:
    return FileResponse(_OAUTH_HOME_CSS, media_type="text/css; charset=utf-8")


def _resolve_updates_dir() -> Path | None:
    """Directorio con latest.json y paquetes firmados para el auto-updater Tauri."""
    candidates: list[Path] = []
    override = _settings.updates_dir.strip()
    if override:
        candidates.append(Path(override))

    backend_dir = Path(__file__).resolve().parent
    candidates.append(backend_dir.parent / "updates")
    candidates.append(Path("/app/static/updates"))
    candidates.append(Path("/var/lib/irrigacion/updates"))

    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "latest.json").is_file():
            return resolved
    return None


_updates_dir = _resolve_updates_dir()
if _updates_dir is not None:
    logger.info("Sirviendo actualizaciones Tauri desde %s", _updates_dir)
    app.mount("/updates", StaticFiles(directory=str(_updates_dir)), name="updates")
else:
    logger.warning(
        "No se encontró updates/latest.json; el auto-updater de Tauri no tendrá "
        "archivos en /updates. Creá la carpeta updates/ en la raíz del repo."
    )


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

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    def pwa_app_shell() -> FileResponse:
        return FileResponse(_frontend_dist / "index.html")

    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="pwa")
else:
    logger.warning(
        "No se encontró desktop-app/dist; la SPA no se servirá en '/app'. "
        "Ejecutá 'npm run build' en desktop-app/ (o definí FRONTEND_DIST_DIR) "
        "para habilitarla."
    )
