"""Punto de entrada FastAPI — irrigacion-bot."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, files, skills
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.is_production:
        settings.assert_production_ready()
    yield


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
