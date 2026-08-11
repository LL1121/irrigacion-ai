"""Caché semántico basado en distancia coseno (pgvector)."""

from __future__ import annotations

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings


def _openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def _embedding_to_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in embedding) + "]"


def embed_query(user_query: str) -> list[float]:
    settings = get_settings()
    client = _openai_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=[user_query],
    )
    return response.data[0].embedding


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
    if distance < threshold:
        return str(row["ai_response"])
    return None


def save_to_semantic_cache(
    db: Session,
    user_query: str,
    query_embedding: list[float],
    ai_response: str,
) -> int:
    """Guarda una entrada en semantic_cache. Retorna el id insertado."""
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
