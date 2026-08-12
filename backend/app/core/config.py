from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"

    database_url: str = (
        "postgresql://postgres:postgres_local_pass@localhost:5434/irrigacion_db"
    )

    # Groq (chat principal — API compatible con OpenAI SDK)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    chat_model: str = "llama-3.3-70b-versatile"

    # Gemini (OCR, embeddings y centinela de skills)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    ocr_model: str = "gemini-flash-latest"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    chunk_size: int = 1000
    chunk_overlap: int = 150
    scanned_pdf_char_threshold: int = 50
    skill_sandbox_image: str = "skill-sandbox-image"
    skill_workspace_dir: str = "/var/lib/irrigacion/skills"
    updates_dir: str = ""

    cors_origins: str = "*"

    # Override opcional del directorio con el build de la PWA (desktop-app/dist).
    # Si queda vacío, main.py lo ubica con rutas relativas conocidas.
    frontend_dist_dir: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.is_production and (not raw or raw == ["*"]):
            raise ValueError(
                "CORS_ORIGINS='*' no está permitido en production. "
                "Definí orígenes explícitos en .env."
            )
        return raw or ["*"]

    def assert_production_ready(self) -> None:
        if not self.is_production:
            return
        placeholders = {
            "",
            "gsk-your-api-key-here",
            "tu_api_key_de_gemini",
            "CAMBIAR_PASSWORD_FUERTE",
        }
        problems: list[str] = []
        if (
            self.groq_api_key.strip() in placeholders
            or self.groq_api_key.startswith("gsk-your")
        ):
            problems.append("GROQ_API_KEY")
        if self.gemini_api_key.strip() in placeholders or self.gemini_api_key.startswith(
            "tu_api_key"
        ):
            problems.append("GEMINI_API_KEY")
        if "postgres_local_pass" in self.database_url:
            problems.append(
                "POSTGRES_PASSWORD (DATABASE_URL todavía usa postgres_local_pass de lab; "
                "definí POSTGRES_PASSWORD en .env)"
            )
        elif "CAMBIAR_PASSWORD" in self.database_url:
            problems.append(
                "POSTGRES_PASSWORD (sigue el placeholder CAMBIAR_PASSWORD_FUERTE; "
                "poné una clave real en .env y, si la DB ya se inicializó con el placeholder, "
                "recreá el volumen: docker compose --env-file .env -f docker-compose.prod.yml down -v)"
            )
        if self.cors_origins.strip() in {"", "*"}:
            problems.append("CORS_ORIGINS")
        if problems:
            raise RuntimeError(
                "Configuración de producción incompleta: " + " | ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
