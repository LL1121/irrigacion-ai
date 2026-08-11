"""Motor del agente LangGraph: retrieve → history → generate (+ persistencia/caché)."""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.cache import embed_query, save_to_semantic_cache

SYSTEM_PROMPT = (
    "Sos el asistente técnico oficial de la oficina de Irrigación de Malargüe. "
    "Respondé únicamente basándote en el contexto proporcionado y el historial. "
    "Sé directo, técnico y profesional. "
    "Si el contexto no alcanza para responder con certeza, indicalo claramente "
    "sin inventar datos, normas ni caudales."
)


class AgentState(TypedDict):
    session_id: str
    user_message: str
    history: list[dict]
    retrieved_docs: list[str]
    query_embedding: list[float]
    reply: str


def _embedding_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in embedding) + "]"


def _retrieve_node(state: AgentState, db: Session) -> dict:
    embedding = embed_query(state["user_message"])
    literal = _embedding_literal(embedding)

    rows = db.execute(
        text(
            """
            SELECT
                document_name,
                content,
                (embedding <=> CAST(:embedding AS vector)) AS distance
            FROM document_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 4
            """
        ),
        {"embedding": literal},
    ).mappings().all()

    docs: list[str] = []
    for row in rows:
        docs.append(
            f"[{row['document_name']} | dist={float(row['distance']):.4f}]\n{row['content']}"
        )

    return {
        "query_embedding": embedding,
        "retrieved_docs": docs,
    }


def _fetch_history_node(state: AgentState, db: Session) -> dict:
    rows = db.execute(
        text(
            """
            SELECT role, message
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            LIMIT 6
            """
        ),
        {"session_id": state["session_id"]},
    ).mappings().all()

    # Orden cronológico ASC para el LLM
    history = [
        {"role": row["role"], "message": row["message"]}
        for row in reversed(list(rows))
    ]
    return {"history": history}


def _generate_node(state: AgentState) -> dict:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )

    context_block = (
        "\n\n---\n\n".join(state["retrieved_docs"])
        if state["retrieved_docs"]
        else "(Sin documentos recuperados en la base vectorial.)"
    )

    messages: list = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(
            content=(
                "Contexto documental recuperado (RAG):\n\n"
                f"{context_block}"
            )
        ),
    ]

    for item in state["history"]:
        role = (item.get("role") or "").lower()
        content = item.get("message") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role in {"assistant", "ai", "system"}:
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=state["user_message"]))

    response = llm.invoke(messages)
    reply = (response.content or "").strip()
    if not reply:
        reply = (
            "No pude generar una respuesta a partir del contexto disponible. "
            "Verificá que haya documentos indexados o reformulá la consulta."
        )
    return {"reply": reply}


def _persist_turn(
    db: Session,
    session_id: str,
    user_message: str,
    reply: str,
    query_embedding: list[float],
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, role, message)
            VALUES (:session_id, :role, :message)
            """
        ),
        {"session_id": session_id, "role": "user", "message": user_message},
    )
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, role, message)
            VALUES (:session_id, :role, :message)
            """
        ),
        {"session_id": session_id, "role": "assistant", "message": reply},
    )
    db.commit()

    if query_embedding:
        save_to_semantic_cache(db, user_message, query_embedding, reply)


def build_agent_graph(db: Session):
    graph = StateGraph(AgentState)

    def retrieve(state: AgentState) -> dict:
        return _retrieve_node(state, db)

    def fetch_history(state: AgentState) -> dict:
        return _fetch_history_node(state, db)

    def generate(state: AgentState) -> dict:
        return _generate_node(state)

    graph.add_node("retrieve", retrieve)
    graph.add_node("fetch_history", fetch_history)
    graph.add_node("generate", generate)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "fetch_history")
    graph.add_edge("fetch_history", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


def run_agent(db: Session, session_id: UUID | str, user_message: str) -> str:
    """Ejecuta el grafo RAG y persiste turno + caché semántico."""
    compiled = build_agent_graph(db)
    sid = str(session_id)

    final_state = compiled.invoke(
        {
            "session_id": sid,
            "user_message": user_message,
            "history": [],
            "retrieved_docs": [],
            "query_embedding": [],
            "reply": "",
        }
    )

    reply = final_state.get("reply") or ""
    _persist_turn(
        db,
        sid,
        user_message,
        reply,
        final_state.get("query_embedding") or [],
    )
    return reply
