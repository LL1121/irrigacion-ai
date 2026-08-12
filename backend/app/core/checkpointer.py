"""Checkpointer LangGraph en Postgres (HITL / interrupt)."""

from __future__ import annotations

import logging

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_checkpointer: PostgresSaver | None = None


def _conninfo() -> str:
    url = get_settings().database_url
    return (
        url.replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


def init_checkpointer() -> PostgresSaver:
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    _pool = ConnectionPool(
        conninfo=_conninfo(),
        min_size=1,
        max_size=8,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    _checkpointer = PostgresSaver(_pool)
    _checkpointer.setup()
    logger.info("Checkpointer LangGraph inicializado en Postgres")
    return _checkpointer


def get_checkpointer() -> PostgresSaver:
    if _checkpointer is None:
        return init_checkpointer()
    return _checkpointer


def close_checkpointer() -> None:
    global _pool, _checkpointer
    if _pool is not None:
        _pool.close()
    _pool = None
    _checkpointer = None
