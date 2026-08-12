from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


def ensure_runtime_schema() -> None:
    """Columnas extra para volúmenes de DB ya inicializados (init.sql no se re-ejecuta)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE chat_messages "
                "ADD COLUMN IF NOT EXISTS metadata JSONB"
            )
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
