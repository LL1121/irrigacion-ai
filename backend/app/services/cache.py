"""Caché semántico basado en distancia coseno (pgvector)."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.ingest import generate_embeddings

# Respuestas de un turno (alcance, aprobación): no son hechos reutilizables.
_SESSION_BOUND_REPLY_RE = re.compile(
    r"contexto personal.{0,120}contexto de irrigaci|"
    r"contexto de irrigaci.{0,120}contexto personal|"
    r"\bautoriz[aá]s\b|"
    r"qu[eé] quer[eé]s que anote",
    re.I | re.S,
)


def _embedding_to_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in embedding) + "]"


def should_use_semantic_cache(user_message: str) -> bool:
    """Solo consultas de conocimiento. Charla, órdenes y HITL no van al caché."""
    from app.services.context_memory import looks_like_save_context_intent
    from app.services.google_assistant import detect_google_intent
    from app.services.skill_marketplace import (
        is_asking_for_needed_data,
        is_casual_chat,
        looks_like_skill_intent,
    )

    blob = (user_message or "").strip()
    if not blob:
        return False
    if is_casual_chat(blob):
        return False
    if looks_like_save_context_intent(blob):
        return False
    if detect_google_intent(blob) is not None:
        return False
    if looks_like_skill_intent(blob) or is_asking_for_needed_data(blob):
        return False
    return True


def is_reusable_knowledge_reply(reply: str) -> bool:
    """Un prompt de decisión del hilo no se reutiliza en otro mensaje."""
    blob = (reply or "").strip()
    if not blob:
        return False
    return not bool(_SESSION_BOUND_REPLY_RE.search(blob))


def cacheable_exchange(user_message: str, reply: str | None = None) -> bool:
    if not should_use_semantic_cache(user_message):
        return False
    if reply is not None and not is_reusable_knowledge_reply(reply):
        return False
    return True


def embed_query(user_query: str) -> list[float]:
    vectors = generate_embeddings([user_query], task_type="RETRIEVAL_QUERY")
    if not vectors:
        raise RuntimeError("No se pudo generar embedding de la consulta")
    return vectors[0]


def check_semantic_cache(
    db: Session,
    user_query: str,
    threshold: float = 0.05,
) -> str | None:
    """
    Calcula el embedding de user_query y busca en semantic_cache.

    Si la distancia coseno (<=>) es menor a threshold (~similitud > 95%),
    retorna ai_response. Si no, retorna None.
    """
    query_embedding = embed_query(user_query)
    embedding_literal = _embedding_to_literal(query_embedding)

    sql = text(
        """
        SELECT
            id,
            ai_response,
            (query_embedding <=> CAST(:embedding AS vector)) AS distance
        FROM semantic_cache
        ORDER BY query_embedding <=> CAST(:embedding AS vector)
        LIMIT 1
        """
    )
    row = db.execute(sql, {"embedding": embedding_literal}).mappings().first()
    if row is None:
        return None

    distance = float(row["distance"])
    if distance >= threshold:
        return None
    response = str(row["ai_response"])
    if is_reusable_knowledge_reply(response):
        return response
    db.execute(
        text("DELETE FROM semantic_cache WHERE id = :id"),
        {"id": int(row["id"])},
    )
    db.commit()
    return None


def save_to_semantic_cache(
    db: Session,
    user_query: str,
    query_embedding: list[float],
    ai_response: str,
) -> int:
    """Guarda una entrada en semantic_cache. Retorna el id insertado."""
    from app.services.skill_marketplace import is_casual_chat

    if is_casual_chat(user_query) or not is_reusable_knowledge_reply(ai_response):
        return 0
    embedding_literal = _embedding_to_literal(query_embedding)
    sql = text(
        """
        INSERT INTO semantic_cache (user_query, query_embedding, ai_response)
        VALUES (:user_query, CAST(:embedding AS vector), :ai_response)
        RETURNING id
        """
    )
    result = db.execute(
        sql,
        {
            "user_query": user_query,
            "embedding": embedding_literal,
            "ai_response": ai_response,
        },
    )
    db.commit()
    return int(result.scalar_one())
