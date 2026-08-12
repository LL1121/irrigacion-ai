from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

_AUDIT_SQL = Path(__file__).resolve().parents[1] / "database" / "audit.sql"


def _apply_sql_script(conn, path: Path) -> None:
    """Ejecuta un script SQL multi-statement (funciones/triggers)."""
    sql = path.read_text(encoding="utf-8")
    dbapi = conn.connection.driver_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def ensure_runtime_schema() -> None:
    """Migraciones ligeras + auditoría para volúmenes ya inicializados."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE chat_messages "
                "ADD COLUMN IF NOT EXISTS metadata JSONB"
            )
        )
        if _AUDIT_SQL.is_file():
            _apply_sql_script(conn, _AUDIT_SQL)
        else:
            raise FileNotFoundError(f"No se encontró el script de auditoría: {_AUDIT_SQL}")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
