"""Motor del agente LangGraph: RAG + búsqueda de skills + HITL + sandbox."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.checkpointer import get_checkpointer
from app.core.config import get_settings
from app.services.cache import embed_query, save_to_semantic_cache
from app.services.document_export import (
    artifact_info,
    save_artifact_from_base64,
)
from app.services.sandbox import execute_skill_in_sandbox_sync
from app.services.skill_marketplace import (
    APPROVAL_KIND_DOWNLOAD,
    APPROVAL_KIND_EXECUTE,
    download_remote_prompt,
    enrich_skill_arguments,
    find_local_skill,
    is_action_request,
    search_catalog,
    search_skill_marketplace,
    should_try_skill_marketplace,
)
from app.services.skill_remote import generate_remote_skill

logger = logging.getLogger(__name__)

STATUS_OK = "agent"
STATUS_APPROVAL = "REQUIRES_APPROVAL"

SYSTEM_PROMPT_IRRIGACION = """
Sos un colega técnico y asistente virtual experto en la oficina de Irrigación de Malargüe.
Tu objetivo es ayudar al personal de la oficina a resolver dudas sobre normativas, padrones, trámites, cálculos hidráulicos y gestión de expedientes.

### PERSONALIDAD Y TONO DE COMUNICACIÓN:
1. **Colega técnico e informado:** Hablá de forma natural, amigable, clara y directa. Olvidate del lenguaje burocrático, rígido o sobrecargado de etiqueta.
2. **CERO ADULACIÓN Y CERO "SÍ A TODO":** No le des la razón al usuario por educación ni alabes sus propuestas si son incorrectas, ineficientes o inviables.
3. **CRÍTICA CRUDA Y HONESTIDAD:** Si el usuario te plantea una idea floja, un cálculo dudoso o un procedimiento que va contra la normativa de Irrigación o las buenas prácticas, decíselo de frente. Señalá la debilidad o el error con respeto técnico, sin rodeos ni palabras bonitas, y proponé la alternativa correcta.
4. **FORMATO FLEXIBLE:** Adaptá el formato de respuesta a lo que pida la situación (pueden ser listas con viñetas, tablas en Markdown para datos numéricos, un resumen de dos oraciones o una explicación técnica detallada). No uses siempre la misma estructura fija.

### LÍMITES, HONESTIDAD Y MANEJO DE INFORMACIÓN:
1. **Prioridad Contexto Local (RAG):** Evaluá primero la información proveniente de los documentos locales de la base de datos de Irrigación.
2. **Búsquedas Externas / Internet:** Si no encontrás la respuesta en la base local y tenés que recurrir a búsquedas web o conocimientos generales fuera del contexto local, es OBLIGATORIO que antecedas o cierres tu respuesta aclarando exactamente esto:
   > "Che, no tengo la información necesaria en la base local de Irrigación, así que la busqué en internet/conocimiento general. Revisá bien la respuesta antes de tomar una decisión institucional."
3. **Prohibido Alucinar:** Si no sabés algo ni podés verificarlo en el contexto provisto, decí directamente que no tenés el dato.

### NIVELES DE HERRAMIENTAS Y PERMISOS:
- Operás por defecto con permisos de nivel ADMINISTRATIVO ALTO. Tenés acceso a herramientas de redacción de documentos, búsquedas en base vectorial y cálculos técnicos.
""".strip()

SKILL_TOOLING_HINT = (
    "Herramientas: no tenés calculadoras locales bindeadas. Si el usuario pide un "
    "cálculo, conversión de unidades, prorrateo de turno, lámina o tiempo de riego, "
    "generación de documentos Word, o cualquier automatización que no puedas resolver "
    "solo con los documentos, DEBÉS llamar a search_skill_marketplace. No inventes "
    "resultados numéricos ni archivos: primero buscá la skill. Extraé números y datos "
    "del mensaje en arguments_json. Si podés responder solo con el contexto RAG, "
    "respondé en texto sin tools."
)

# Alias retrocompatible: el resto del módulo referenciaba SYSTEM_PROMPT.
SYSTEM_PROMPT = SYSTEM_PROMPT_IRRIGACION

SPEED_MODE_TOP_K: dict[str, int] = {
    "fast": 2,
    "balanced": 5,
    "deep": 10,
}
DEFAULT_SPEED_MODE = "deep"


def _resolve_top_k(speed_mode: str | None) -> int:
    return SPEED_MODE_TOP_K.get((speed_mode or DEFAULT_SPEED_MODE).lower(), SPEED_MODE_TOP_K[DEFAULT_SPEED_MODE])

CATALOG_HINT = (
    "Catálogo de skills (buscar con search_skill_marketplace): "
    "Cálculo de caudal (Q = A·v); Conversión de unidades de caudal; "
    "Prorrateo de turno de riego; Lámina de riego; Tiempo de riego; "
    "Generación de documento Word (.docx)."
)


class AgentState(TypedDict):
    session_id: str
    user_message: str
    speed_mode: NotRequired[str]
    history: list[dict]
    retrieved_docs: list[str]
    query_embedding: list[float]
    reply: str
    pending_skill: NotRequired[dict[str, Any] | None]
    needs_approval: NotRequired[bool]
    skill_approved: NotRequired[bool | None]
    skill_result: NotRequired[dict[str, Any] | None]
    attachments: NotRequired[list[dict[str, Any]]]
    approval_kind: NotRequired[str | None]
    download_approved: NotRequired[bool | None]


@dataclass
class AgentOutcome:
    status: str
    reply: str
    skill_name: str | None = None
    skill_description: str | None = None
    from_cache: bool = False
    audit: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None
    approval_kind: str | None = None


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": str(session_id)}}


def _embedding_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in embedding) + "]"


def _llm(*, tools: bool = False) -> ChatOpenAI:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        temperature=0.2,
    )
    if tools:
        return llm.bind_tools([search_skill_marketplace])
    return llm


def _context_block(docs: list[str]) -> str:
    if docs:
        return "\n\n---\n\n".join(docs)
    return "(Sin documentos recuperados en la base vectorial.)"


def _history_messages(history: list[dict]) -> list:
    messages: list = []
    for item in history:
        role = (item.get("role") or "").lower()
        content = item.get("message") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role in {"assistant", "ai", "system"}:
            messages.append(AIMessage(content=content))
    return messages


def _retrieve_node(state: AgentState, db: Session) -> dict:
    embedding = embed_query(state["user_message"])
    literal = _embedding_literal(embedding)
    top_k = _resolve_top_k(state.get("speed_mode"))

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
            LIMIT :top_k
            """
        ),
        {"embedding": literal, "top_k": top_k},
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

    history = [
        {"role": row["role"], "message": row["message"]}
        for row in reversed(list(rows))
    ]
    return {"history": history}


def _parse_tool_arguments(raw_args: dict[str, Any], user_message: str) -> tuple[str, dict]:
    task = str(raw_args.get("task") or user_message)
    arguments = raw_args.get("arguments") or raw_args.get("arguments_json") or {}
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            arguments = parsed if isinstance(parsed, dict) else {"valor": parsed}
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {"valor": arguments}
    if not arguments:
        arguments = {"query": user_message}
    return task, arguments


def _resolve_skill_plan(task: str, arguments: dict[str, Any], user_message: str) -> dict[str, Any] | None:
    """Evalúa skills locales; si no hay match y es un pedido de acción, pide descarga."""
    if not (is_action_request(user_message) or should_try_skill_marketplace(user_message)):
        return None
    found = find_local_skill(task, arguments)
    if found.get("found"):
        return {
            "pending_skill": found,
            "approval_kind": APPROVAL_KIND_EXECUTE,
            "needs_approval": True,
            "reply": "",
        }
    return {
        "pending_skill": None,
        "approval_kind": APPROVAL_KIND_DOWNLOAD,
        "needs_approval": True,
        "reply": "",
    }


def _plan_node(state: AgentState) -> dict:
    llm = _llm(tools=True)
    messages: list = [
        SystemMessage(content=SYSTEM_PROMPT_IRRIGACION),
        SystemMessage(content=SKILL_TOOLING_HINT),
        SystemMessage(content=CATALOG_HINT),
        SystemMessage(
            content="Contexto documental recuperado (RAG):\n\n"
            + _context_block(state.get("retrieved_docs") or [])
        ),
        *_history_messages(state.get("history") or []),
        HumanMessage(content=state["user_message"]),
    ]
    response = llm.invoke(messages)
    tool_calls = getattr(response, "tool_calls", None) or []

    for call in tool_calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if name != "search_skill_marketplace":
            continue
        raw_args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
        task, arguments = _parse_tool_arguments(raw_args or {}, state["user_message"])
        resolved = _resolve_skill_plan(task, arguments, state["user_message"])
        if resolved:
            return resolved
        if is_action_request(state["user_message"]):
            return {
                "pending_skill": None,
                "approval_kind": APPROVAL_KIND_DOWNLOAD,
                "needs_approval": True,
                "reply": "",
            }
        available = ", ".join(
            s["name"] for s in search_catalog(task, arguments).get("available") or []
        )
        return {
            "pending_skill": None,
            "needs_approval": False,
            "reply": (
                "No encontré una skill en el catálogo para esa tarea. "
                f"Disponibles: {available or '(ninguna)'}."
            ),
        }

    reply = (getattr(response, "content", None) or "").strip()
    resolved = _resolve_skill_plan(
        state["user_message"], {"query": state["user_message"]}, state["user_message"]
    )
    if resolved:
        return resolved
    if should_try_skill_marketplace(state["user_message"], reply):
        fallback = find_local_skill(state["user_message"], {"query": state["user_message"]})
        if fallback.get("found"):
            return {
                "pending_skill": fallback,
                "approval_kind": APPROVAL_KIND_EXECUTE,
                "needs_approval": True,
                "reply": "",
            }
        if is_action_request(state["user_message"]):
            return {
                "pending_skill": None,
                "approval_kind": APPROVAL_KIND_DOWNLOAD,
                "needs_approval": True,
                "reply": "",
            }
    if not reply:
        reply = (
            "No pude generar una respuesta a partir del contexto disponible. "
            "Verificá que haya documentos indexados o reformulá la consulta."
        )
    return {
        "pending_skill": None,
        "needs_approval": False,
        "reply": reply,
    }


def _route_after_plan(state: AgentState) -> Literal["human_gate_download", "human_gate_execute", "end_ok"]:
    kind = state.get("approval_kind")
    if kind == APPROVAL_KIND_DOWNLOAD:
        return "human_gate_download"
    if kind == APPROVAL_KIND_EXECUTE and state.get("pending_skill"):
        return "human_gate_execute"
    return "end_ok"


def _approval_prompt(skill: dict[str, Any]) -> str:
    name = skill.get("name") or "desconocida"
    source = skill.get("source")
    prefix = "Se descargó la skill" if source == "remote" else "Se encontró la skill"
    return (
        f"No tengo esta habilidad instalada. {prefix} '{name}'. "
        "¿Autorizás a Gemini a auditarla y ejecutarla en el sandbox?"
    )


def _interrupt_to_prompt(payload: dict[str, Any], values: dict[str, Any]) -> str:
    kind = payload.get("approval_kind") or payload.get("intent")
    if kind == APPROVAL_KIND_DOWNLOAD:
        return download_remote_prompt()
    skill = values.get("pending_skill") or {}
    return _approval_prompt(
        {
            "name": payload.get("skill_name") or skill.get("name"),
            "source": skill.get("source"),
        }
    )


def _human_gate_download_node(state: AgentState) -> dict:
    decision = interrupt(
        {
            "intent": APPROVAL_KIND_DOWNLOAD,
            "approval_kind": APPROVAL_KIND_DOWNLOAD,
            "task": state["user_message"],
        }
    )
    approved = (
        bool(decision.get("approved"))
        if isinstance(decision, dict)
        else bool(decision)
    )
    if not approved:
        return {
            "download_approved": False,
            "reply": "Entendido. No voy a descargar esa habilidad desde internet.",
            "needs_approval": False,
            "approval_kind": None,
        }
    return {"download_approved": True}


def _route_after_download_gate(state: AgentState) -> Literal["fetch_remote_skill", "end_ok"]:
    if state.get("download_approved"):
        return "fetch_remote_skill"
    return "end_ok"


def _fetch_remote_skill_node(state: AgentState) -> dict:
    try:
        skill = generate_remote_skill(
            state["user_message"],
            rag_context=_context_block(state.get("retrieved_docs") or []),
        )
    except Exception as exc:
        logger.exception("Fallo al descargar skill remota")
        return {
            "reply": f"No pude descargar la habilidad: {exc}",
            "needs_approval": False,
            "approval_kind": None,
        }
    return {
        "pending_skill": skill,
        "approval_kind": APPROVAL_KIND_EXECUTE,
        "needs_approval": True,
    }


def _route_after_fetch(state: AgentState) -> Literal["human_gate_execute", "end_ok"]:
    if state.get("needs_approval") and state.get("pending_skill"):
        return "human_gate_execute"
    return "end_ok"


def _human_gate_execute_node(state: AgentState) -> dict:
    skill = state.get("pending_skill") or {}
    decision = interrupt(
        {
            "intent": APPROVAL_KIND_EXECUTE,
            "approval_kind": APPROVAL_KIND_EXECUTE,
            "skill_id": skill.get("id"),
            "skill_name": skill.get("name"),
            "skill_description": skill.get("description"),
        }
    )
    if isinstance(decision, dict):
        approved = bool(decision.get("approved"))
    else:
        approved = bool(decision)
    return {"skill_approved": approved}


def _run_skill_node(state: AgentState) -> dict:
    if not state.get("skill_approved"):
        return {
            "skill_result": None,
            "reply": (
                "Entendido. No instalé ni ejecuté la skill porque cancelaste "
                "la autorización."
            ),
        }

    skill = dict(state.get("pending_skill") or {})
    skill["arguments"] = enrich_skill_arguments(skill, state["user_message"])
    code = skill.get("code") or ""
    arguments = skill.get("arguments") or {}
    try:
        result = execute_skill_in_sandbox_sync(code, arguments)
    except Exception as exc:
        logger.exception("Fallo al ejecutar skill en sandbox")
        name = skill.get("name") or "skill"
        return {
            "skill_result": {
                "status": "error",
                "audit": None,
                "execution": {"error": str(exc)},
            },
            "reply": (
                f"No pude ejecutar la skill '{name}': {exc}. "
                "Si falta la imagen del sandbox, en el servidor corré: "
                "docker build -t skill-sandbox-image backend/sandbox_env"
            ),
            "pending_skill": skill,
        }
    return {"skill_result": result, "reply": "", "pending_skill": skill}


def _skill_result_payload(execution: dict[str, Any]) -> dict[str, Any] | None:
    parsed = execution.get("parsed")
    if not isinstance(parsed, dict):
        return None
    inner = parsed.get("result")
    if isinstance(inner, dict):
        if inner.get("content_base64") or inner.get("files"):
            return inner
        return inner
    return parsed if parsed.get("content_base64") or parsed.get("files") else None


def _persist_skill_attachments(skill_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not skill_data:
        return []
    attachments: list[dict[str, Any]] = []

    def _save_one(payload: dict[str, Any]) -> None:
        b64 = payload.get("content_base64")
        if not b64:
            return
        filename = str(payload.get("filename") or "archivo")
        mime = payload.get("mime")
        try:
            file_id, _ = save_artifact_from_base64(str(b64), filename, mime=mime)
            info = artifact_info(file_id) or {}
            attachments.append(
                {
                    "file_id": file_id,
                    "filename": info.get("filename") or filename,
                    "mime": info.get("mime") or mime or "application/octet-stream",
                    "size_bytes": info.get("size_bytes"),
                }
            )
        except Exception:
            logger.exception("No se pudo persistir el archivo generado por la skill")

    files = skill_data.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                _save_one(item)
    else:
        _save_one(skill_data)
    return attachments


def _compose_skill_reply_node(state: AgentState) -> dict:
    if state.get("reply"):
        return {}

    result = state.get("skill_result") or {}
    skill = state.get("pending_skill") or {}
    name = skill.get("name") or "skill"

    if result.get("status") == "rejected":
        audit = result.get("audit") or {}
        reason = audit.get("reason") or "riesgo detectado"
        return {
            "reply": (
                f"Gemini rechazó la skill '{name}' (auditoría de seguridad): {reason}"
            )
        }

    if result.get("status") == "error":
        execution = result.get("execution") or {}
        err = execution.get("error") or "error desconocido"
        return {
            "reply": (
                f"No pude ejecutar la skill '{name}': {err}. "
                "Si falta la imagen del sandbox, en el servidor corré: "
                "docker build -t skill-sandbox-image backend/sandbox_env"
            )
        }

    execution = result.get("execution") or {}
    parsed = execution.get("parsed")
    payload = json.dumps(parsed if parsed is not None else execution, ensure_ascii=False, indent=2)

    llm = _llm(tools=False)
    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Sos el asistente técnico de Irrigación de Malargüe. "
                    "Presentá el resultado de la skill de forma clara y profesional. "
                    "No inventes valores que no estén en el JSON."
                )
            ),
            HumanMessage(
                content=(
                    f"El usuario pidió: {state['user_message']}\n"
                    f"Skill ejecutada: {name}\n"
                    f"Argumentos: {json.dumps(skill.get('arguments') or {}, ensure_ascii=False)}\n"
                    f"Resultado del sandbox:\n{payload}"
                )
            ),
        ]
    )
    reply = (getattr(response, "content", None) or "").strip()
    if not reply:
        reply = f"Resultado de '{name}':\n{payload}"
    skill_data = _skill_result_payload(execution)
    attachments = _persist_skill_attachments(skill_data)
    if attachments:
        names = ", ".join(a["filename"] for a in attachments)
        reply = f"{reply}\n\nGeneré el archivo: {names}. Podés abrirlo desde el visor debajo."
    return {"reply": reply, "attachments": attachments}


def _persist_message(
    db: Session,
    session_id: str,
    role: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, role, message, metadata)
            VALUES (:session_id, :role, :message, CAST(:metadata AS jsonb))
            """
        ),
        {
            "session_id": session_id,
            "role": role,
            "message": message,
            "metadata": json.dumps(metadata, ensure_ascii=False) if metadata else None,
        },
    )
    db.commit()


def extract_interrupt_payload(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    interrupts = getattr(snapshot, "interrupts", None) or ()
    if interrupts:
        first = interrupts[0]
        value = getattr(first, "value", first)
        return value if isinstance(value, dict) else None
    tasks = getattr(snapshot, "tasks", None) or ()
    for task in tasks:
        task_interrupts = getattr(task, "interrupts", None) or ()
        if task_interrupts:
            value = getattr(task_interrupts[0], "value", None)
            if isinstance(value, dict):
                return value
    values = getattr(snapshot, "values", None) or {}
    if values.get("approval_kind") == APPROVAL_KIND_DOWNLOAD:
        return {
            "intent": APPROVAL_KIND_DOWNLOAD,
            "approval_kind": APPROVAL_KIND_DOWNLOAD,
            "task": values.get("user_message"),
        }
    if values.get("needs_approval") and values.get("pending_skill"):
        skill = values["pending_skill"]
        return {
            "intent": APPROVAL_KIND_EXECUTE,
            "approval_kind": APPROVAL_KIND_EXECUTE,
            "skill_id": skill.get("id"),
            "skill_name": skill.get("name"),
            "skill_description": skill.get("description"),
        }
    return None


def build_agent_graph(db: Session):
    graph = StateGraph(AgentState)

    def retrieve(state: AgentState) -> dict:
        return _retrieve_node(state, db)

    def fetch_history(state: AgentState) -> dict:
        return _fetch_history_node(state, db)

    graph.add_node("retrieve", retrieve)
    graph.add_node("fetch_history", fetch_history)
    graph.add_node("plan", _plan_node)
    graph.add_node("human_gate_download", _human_gate_download_node)
    graph.add_node("fetch_remote_skill", _fetch_remote_skill_node)
    graph.add_node("human_gate_execute", _human_gate_execute_node)
    graph.add_node("run_skill", _run_skill_node)
    graph.add_node("compose_skill_reply", _compose_skill_reply_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "fetch_history")
    graph.add_edge("fetch_history", "plan")
    graph.add_conditional_edges(
        "plan",
        _route_after_plan,
        {
            "human_gate_download": "human_gate_download",
            "human_gate_execute": "human_gate_execute",
            "end_ok": END,
        },
    )
    graph.add_conditional_edges(
        "human_gate_download",
        _route_after_download_gate,
        {"fetch_remote_skill": "fetch_remote_skill", "end_ok": END},
    )
    graph.add_conditional_edges(
        "fetch_remote_skill",
        _route_after_fetch,
        {"human_gate_execute": "human_gate_execute", "end_ok": END},
    )
    graph.add_edge("human_gate_execute", "run_skill")
    graph.add_edge("run_skill", "compose_skill_reply")
    graph.add_edge("compose_skill_reply", END)

    return graph.compile(checkpointer=get_checkpointer())


def get_pending_approval(db: Session, session_id: UUID | str) -> dict[str, Any] | None:
    compiled = build_agent_graph(db)
    snapshot = compiled.get_state(_thread_config(str(session_id)))
    return extract_interrupt_payload(snapshot)


def run_agent(
    db: Session,
    session_id: UUID | str,
    user_message: str,
    speed_mode: str | None = DEFAULT_SPEED_MODE,
) -> AgentOutcome:
    """Ejecuta el grafo. Puede devolver REQUIRES_APPROVAL si hay HITL."""
    compiled = build_agent_graph(db)
    sid = str(session_id)
    config = _thread_config(sid)
    resolved_speed_mode = (speed_mode or DEFAULT_SPEED_MODE).lower()
    if resolved_speed_mode not in SPEED_MODE_TOP_K:
        resolved_speed_mode = DEFAULT_SPEED_MODE

    pending = extract_interrupt_payload(compiled.get_state(config))
    if pending:
        values = getattr(compiled.get_state(config), "values", None) or {}
        prompt = _interrupt_to_prompt(pending, values)
        kind = pending.get("approval_kind")
        skill = values.get("pending_skill") or {}
        name = pending.get("skill_name") or skill.get("name")
        description = pending.get("skill_description") or skill.get("description")
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name if kind == APPROVAL_KIND_EXECUTE else None,
            skill_description=description if kind == APPROVAL_KIND_EXECUTE else None,
            approval_kind=kind,
        )

    try:
        compiled.invoke(
            {
                "session_id": sid,
                "user_message": user_message,
                "speed_mode": resolved_speed_mode,
                "history": [],
                "retrieved_docs": [],
                "query_embedding": [],
                "reply": "",
                "pending_skill": None,
                "needs_approval": False,
                "skill_approved": None,
                "skill_result": None,
                "attachments": [],
                "approval_kind": None,
                "download_approved": None,
            },
            config,
        )
    except Exception as exc:
        if type(exc).__name__ not in {"GraphInterrupt", "NodeInterrupt"}:
            raise
        logger.debug("Grafo interrumpido para HITL: %s", exc)

    snapshot = compiled.get_state(config)
    interrupt_payload = extract_interrupt_payload(snapshot)
    values = getattr(snapshot, "values", None) or {}

    if interrupt_payload:
        skill = values.get("pending_skill") or {}
        kind = interrupt_payload.get("approval_kind")
        prompt = _interrupt_to_prompt(interrupt_payload, values)
        name = interrupt_payload.get("skill_name") or skill.get("name")
        description = (
            interrupt_payload.get("skill_description") or skill.get("description")
        )
        _persist_message(db, sid, "user", user_message)
        _persist_message(
            db,
            sid,
            "assistant",
            prompt,
            {
                "kind": "requires_approval",
                "status": STATUS_APPROVAL,
                "approval_kind": kind,
                "skill_name": name,
                "skill_description": description,
            },
        )
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name if kind == APPROVAL_KIND_EXECUTE else None,
            skill_description=description if kind == APPROVAL_KIND_EXECUTE else None,
            approval_kind=kind,
        )

    reply = values.get("reply") or ""
    attachments = values.get("attachments") or []
    embedding = values.get("query_embedding") or []
    _persist_message(db, sid, "user", user_message)
    assistant_meta: dict[str, Any] | None = None
    if attachments:
        assistant_meta = {"attachments": attachments}
    _persist_message(db, sid, "assistant", reply, assistant_meta)
    if embedding:
        save_to_semantic_cache(db, user_message, embedding, reply)
    return AgentOutcome(status=STATUS_OK, reply=reply, attachments=attachments or None)


def _is_graph_interrupt(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"GraphInterrupt", "NodeInterrupt"}:
        return True
    # Algunas versiones envuelven el interrupt en ExceptionGroup / RuntimeError.
    text = str(exc)
    return "Interrupt" in name or "Interrupt" in text


def resume_agent(db: Session, session_id: UUID | str, approved: bool) -> AgentOutcome:
    """Reanuda el grafo tras Autorizar / Cancelar."""
    compiled = build_agent_graph(db)
    sid = str(session_id)
    config = _thread_config(sid)

    pending = extract_interrupt_payload(compiled.get_state(config))
    if not pending:
        raise RuntimeError("No hay una skill pendiente de autorización en esta sesión.")

    try:
        compiled.invoke(Command(resume={"approved": approved}), config)
    except Exception as exc:
        if not _is_graph_interrupt(exc):
            logger.exception("Error al reanudar el grafo de skills (approved=%s)", approved)
            raise
        logger.debug("Grafo interrumpido tras resume HITL: %s", exc)
    snapshot = compiled.get_state(config)
    values = getattr(snapshot, "values", None) or {}
    interrupt_payload = extract_interrupt_payload(snapshot)

    if interrupt_payload:
        prompt = _interrupt_to_prompt(interrupt_payload, values)
        kind = interrupt_payload.get("approval_kind")
        skill = values.get("pending_skill") or {}
        name = interrupt_payload.get("skill_name") or skill.get("name")
        description = interrupt_payload.get("skill_description") or skill.get("description")
        _persist_message(
            db,
            sid,
            "assistant",
            prompt,
            {
                "kind": "requires_approval",
                "status": STATUS_APPROVAL,
                "approval_kind": kind,
                "skill_name": name,
                "skill_description": description,
            },
        )
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name if kind == APPROVAL_KIND_EXECUTE else None,
            skill_description=description if kind == APPROVAL_KIND_EXECUTE else None,
            approval_kind=kind,
        )

    reply = values.get("reply") or ""
    attachments = values.get("attachments") or []
    skill_result = values.get("skill_result") or {}
    audit = (skill_result or {}).get("audit") if isinstance(skill_result, dict) else None
    user_message = values.get("user_message") or ""
    embedding = values.get("query_embedding") or []

    meta: dict[str, Any] = {
        "kind": "skill_result" if approved else "skill_denied",
        "approved": approved,
        "audit": audit,
    }
    if attachments:
        meta["attachments"] = attachments
    if reply:
        _persist_message(
            db,
            sid,
            "assistant",
            reply,
            meta,
        )
    if approved and embedding and reply:
        save_to_semantic_cache(db, user_message, embedding, reply)

    return AgentOutcome(
        status="executed" if approved else "denied",
        reply=reply,
        skill_name=pending.get("skill_name"),
        skill_description=pending.get("skill_description"),
        audit=audit,
        attachments=attachments or None,
        approval_kind=pending.get("approval_kind"),
    )
