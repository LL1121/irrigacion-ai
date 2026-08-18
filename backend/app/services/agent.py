"""Motor del agente LangGraph: RAG + búsqueda de skills + HITL + sandbox."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.checkpointer import get_checkpointer
from app.core.config import get_settings
from app.services.cache import cacheable_exchange, embed_query, save_to_semantic_cache
from app.services.context_memory import (
    ask_scope_prompt,
    clear_pending_note,
    confirm_saved_message,
    extract_note_body,
    get_pending_note,
    looks_like_save_context_intent,
    parse_context_scope,
    save_context_note,
    set_pending_note,
)
from app.services.document_export import (
    artifact_info,
    save_artifact_from_base64,
)
from app.services.command_router import (
    GOOGLE_ACTIONS,
    infer_google_action,
    missing_google_slots,
    should_use_native_google,
)
from app.services.order_parse import (
    extract_order_parts,
    looks_like_do_task,
    merge_args_with_order,
    OrderParts,
)
from app.services.google_assistant import (
    APPROVAL_KIND_GOOGLE_TOOL,
    build_pending_google_tool,
    execute_google_tool,
    google_write_needs_hitl,
)
from app.services.google_workspace import (
    drive_read_text_file,
    drive_search_files,
    google_oauth_configured,
)
from app.services.response_normalize import (
    classify_skill_payload,
    fallback_skill_reply,
    humanize_skill_payload,
    llm_skill_narration_prompt,
    looks_raw_technical,
    normalize_assistant_reply,
    unwrap_result,
)
from app.services.sandbox import evaluate_skill_audit_sync, execute_skill_sync
from app.services.skill_staging import (
    APPROVAL_KIND_NETWORK,
    AUDIT_RETRY_PROMPT,
    STATUS_APPROVED,
    STATUS_DOWNLOADED,
    STATUS_FAILED,
    STATUS_PENDING_AUDIT,
    STATUS_REQUIRES_PERMISSION,
    get_retryable_staging,
    is_audit_retry,
    network_permission_prompt,
    skill_from_staging,
    upsert_skill_staging,
)
from app.services.skill_marketplace import (
    APPROVAL_KIND_DOWNLOAD,
    APPROVAL_KIND_EXECUTE,
    ask_inputs_for_open_task,
    conversation_context_text,
    detect_response_style,
    is_casual_chat,
    download_remote_prompt,
    extract_open_task,
    find_local_skill,
    is_action_request,
    is_asking_for_needed_data,
    is_context_switch,
    is_result_challenge_or_correction,
    looks_like_skill_intent,
    looks_like_web_or_external_request,
    clarifying_question_for_skill,
    prepare_skill_arguments,
    reply_is_capability_refusal,
    resolve_skill_decision,
    search_catalog,
    skill_missing_required_inputs,
    thread_brief_for_prompt,
)
from app.services.skill_remote import (
    generate_remote_skill,
    resolve_reusable_remote_skill,
    validate_remote_skill,
)
from app.services.skill_whitelist import can_auto_reuse_skill, is_whitelisted
from app.services.llm_roles import chat_llm
from app.services.thread_memory import (
    load_thread_state,
    open_task_from_state,
    recent_history_for_llm,
    schedule_refresh,
)
from app.services.token_guard import (
    dumps_capped,
    enforce_request_budget,
    fit_history,
    fit_rag_docs,
    fit_system_prompt,
    fit_user_message,
    sanitize_json_for_llm,
    token_budget,
)

logger = logging.getLogger(__name__)

STATUS_OK = "agent"
STATUS_APPROVAL = "REQUIRES_APPROVAL"

SYSTEM_PROMPT_IRRIGACION = """
Sos Irrigación Bot, el asistente técnico de la oficina de Irrigación de Malargüe.
Hablás como un modelo de chat moderno (ChatGPT, Gemini): natural, directo, cálido y útil.
Mismo registro que el usuario (rioplatense si habla así; más formal si viene formal).

### VOZ Y PERSONALIDAD:
- Contestá al último mensaje, en el hilo. No arranques de cero sin necesidad.
- Sé cercano y práctico, no distante ni con tono de call center / mesa de ayuda.
- Saludo → saludá corto (1-2 líneas), tipo “todo bien, ¿qué se ofrece?”. Prohibido
  “¿en qué puedo ayudarte?”, “quedó a tu disposición” o frases de mesa de ayuda.
- Tarea → hacela y contá qué hiciste. No anuncies procedimientos internos, estados de carga ni menús de opciones.
- No sos un bot de tickets ni un personaje: no inventes vida personal, fin de semana, humor forzado, ni una receta fija de saludo.
- Prohibido narrar tu estado interno (“estoy funcionando”, “no hay una acción/petición pendiente”, “consulta relacionada con la oficina”).
- Cero adulación: si una propuesta o idea del usuario es floja o va contra la normativa/buenas prácticas, decíselo de frente con criterio técnico y proponé la alternativa correcta.
- Formato: el que pida la situación. Si no pidieron nada específico, sé conciso y no armes informes innecesarios.

### GESTIÓN DE LABURO Y CAMBIO DE CONTEXTO:
1. **Toda la orden cuenta:** qué, a quién, qué decir, a qué hora, formato. No tires datos sueltos a medias.
2. **Pedí solo lo que falta:** no hagas cuestionarios largos si podés avanzar con lo que tenés.
3. **Seguimiento inteligente del hilo:**
   - Si hay una tarea en curso y el usuario responde sobre ella, dale continuidad.
   - Si el usuario plantea una solicitud, orden o tema nuevo e independiente, **cambiá de contexto de inmediato**, soltá el pendiente anterior y ejecutá lo nuevo sin exigir datos del trámite viejo.

### LÍMITES, HONESTIDAD Y MANEJO DE INFORMACIÓN:
1. **Prioridad Contexto Local (RAG):** Evaluá primero la información proveniente de los documentos locales de la base de datos de Irrigación.
2. **Búsquedas Externas / Internet:** Solo aplica a consultas de dato/norma/hecho institucional.
   En charla casual no uses este disclaimer. Si no encontrás la respuesta en la base local
   y recurrís a web o conocimiento general, aclará explícitamente:
   > "Che, no tengo la información necesaria en la base local de Irrigación, así que la busqué en internet/conocimiento general. Revisá bien la respuesta antes de tomar una decisión institucional."
3. **Prohibido Alucinar:** Si no sabés algo ni podés verificarlo en el contexto provisto, decí directamente que no tenés el dato.

### NIVELES DE HERRAMIENTAS Y PERMISOS:
- Operás con permisos de nivel ADMINISTRATIVO ALTO.
- Mail / Gmail / Calendar / Drive → tool `use_google` (nunca una skill para un mail).
- Word, Excel, red, cálculos, scraping, automatizaciones → `search_skill_marketplace`
  (scripts Python del sandbox / marketplace interno).
- Guardar nota tipada → solo si pidió explícito anotar/recordar (`save_user_context`).

### CAPACIDADES EXTENDIDAS, SKILLS Y SANDBOX:
1. **Concepto de Skill:** "skill", "herramienta" o "script" = extensiones Python del
   Sandbox Docker / marketplace interno. Prohibido mencionar Amazon Alexa, Google Assistant,
   Siri, Cortana u otros asistentes de voz.
2. **Proactividad (prohibido rendirse):** Si pide una tarea técnica o automatización
   (Word/Excel, test de red, conversiones, scraping, cálculos) y no tenés tool nativa:
   - NUNCA digas "como modelo de lenguaje no puedo…".
   - Invocá ya `search_skill_marketplace` con las palabras clave de la tarea.
""".strip()

VOICE_HINT = (
    "Hablá como un asistente de chat cálido: natural, cercano, en el hilo. "
    "Ni sistema ('estoy funcionando', 'no hay una acción', '¿en qué puedo ayudarte?') "
    "ni personaje (finde, anécdotas, chistes que no pegan)."
)

CASUAL_SYSTEM = """
Este turno es charla, no una orden. Hablá como un asistente de chat
cálido (ChatGPT, Gemini): natural, breve, mismo registro que el usuario.

- Respondé al último mensaje (1-3 líneas). Sin receta fija.
- Si te saludan o preguntan cómo estás, devolvé el saludo con calidez
  (ej. “todo bien, ¿qué se ofrece?”). Nada de “¿en qué puedo ayudarte?”.
- Si te piden que expliques algo que dijiste, explicalo. No improvises otra bit.
- No inventes biografía ni humor que no viene a cuento.
- No expliques que no hay tarea, que estás funcionando, ni listes capacidades.
""".strip()

NATIVE_TOOLS_HINT = (
    "Si el mensaje es charla, NO uses tools: contestá como persona. "
    "Si hay orden: cumplí TODA (qué, a quién, cuándo, cómo). "
    "Horario ('en 5 minutos') → confirmalo, no lo hagas ahora. "
    "Mail/Gmail/Calendar/Drive → use_google. NUNCA una skill para un mail. "
    "save_user_context SOLO si pidió explícito guardar/anotar/recordar."
)

SKILL_TOOLING_HINT = (
    "Orden operativa (el system prompt ya define skills): "
    "tarea técnica/automatizar → search_skill_marketplace YA; "
    "si no hay local, descarga/generá (HITL). Nunca 'no puedo'. "
    "Delay pedido → confirmalo. open_task vacío/'Ninguna' = sin trámite viejo."
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
    "Generación de documento Word (.docx) con formato (títulos, listas, tablas)."
)


class AgentState(TypedDict):
    session_id: str
    user_message: str
    speed_mode: NotRequired[str]
    user_id: NotRequired[str | None]
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
    pending_google_tool: NotRequired[dict[str, Any] | None]
    google_approved: NotRequired[bool | None]
    pre_assist_done: NotRequired[bool]
    run_at: NotRequired[str | None]
    order_ack: NotRequired[str | None]
    thread_state: NotRequired[dict[str, Any]]
    allow_network: NotRequired[bool]
    retry_staged_audit: NotRequired[bool]


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


def _llm(*, tools: bool = False, temperature: float = 0.2):
    return chat_llm(tools=tools, temperature=temperature)


def _thread_state(state: AgentState | dict[str, Any] | None) -> dict[str, Any]:
    raw = (state or {}).get("thread_state") if state else None
    return raw if isinstance(raw, dict) else {}


def _context_block(docs: list[str]) -> str:
    fitted = fit_rag_docs(docs)
    if fitted:
        return "\n\n---\n\n".join(fitted)
    return "(Sin documentos recuperados en la base vectorial.)"


def _history_messages(
    history: list[dict],
    thread_state: dict[str, Any] | None = None,
) -> list:
    messages: list = []
    for item in fit_history(recent_history_for_llm(history, thread_state)):
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
    user_id = state.get("user_id")

    rows = db.execute(
        text(
            """
            SELECT
                document_name,
                content,
                scope,
                (embedding <=> CAST(:embedding AS vector)) AS distance
            FROM document_chunks
            WHERE embedding IS NOT NULL
              AND (
                    scope = 'irrigacion'
                    OR (
                        scope = 'personal'
                        AND :user_id IS NOT NULL
                        AND user_id = CAST(:user_id AS uuid)
                    )
              )
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        ),
        {"embedding": literal, "top_k": top_k, "user_id": user_id},
    ).mappings().all()

    docs: list[str] = []
    for row in rows:
        scope = row.get("scope") or "irrigacion"
        docs.append(
            f"[{row['document_name']} | {scope} | dist={float(row['distance']):.4f}]\n"
            f"{row['content']}"
        )

    return {
        "query_embedding": embedding,
        "retrieved_docs": docs,
    }


def _save_scoped_note(
    db: Session,
    *,
    content: str,
    scope: str,
    user_id: str | None,
) -> str:
    if scope == "personal" and not user_id:
        return (
            "Para guardar contexto **personal** necesitás iniciar sesión con Google. "
            "Si preferís, decime **irrigación** y lo guardo compartido en la oficina."
        )
    try:
        save_context_note(db, content, scope=scope, user_id=user_id)
    except ValueError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo al guardar contexto tipado")
        return f"No pude guardar el contexto: {exc}"
    return confirm_saved_message(scope)


def _handle_drive_index_to_context(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    pending: dict[str, Any],
) -> dict:
    args = pending.get("arguments") or {}
    file_id = str(args.get("file_id") or "").strip()
    try:
        if not file_id:
            hits = drive_search_files(
                db, user_id, query=str(args.get("search") or args.get("query") or "")
            )
            if not hits:
                return {
                    "reply": (
                        "No encontré un archivo en Drive para indexar. "
                        "Pasame el ID o un nombre más preciso."
                    ),
                    "pre_assist_done": True,
                    "needs_approval": False,
                    "approval_kind": None,
                    "pending_google_tool": None,
                }
            file_id = str(hits[0].get("id") or "")
        data = drive_read_text_file(db, user_id, file_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "reply": f"No pude leer el archivo de Drive: {exc}",
            "pre_assist_done": True,
            "needs_approval": False,
            "approval_kind": None,
            "pending_google_tool": None,
        }
    body = (data.get("text") or "").strip()
    title = data.get("name") or "archivo Drive"
    if not body:
        return {
            "reply": f"El archivo «{title}» no tiene texto legible para indexar.",
            "pre_assist_done": True,
            "needs_approval": False,
            "approval_kind": None,
            "pending_google_tool": None,
        }
    set_pending_note(session_id, f"[{title}]\n{body[:8000]}")
    return {
        "reply": (
            f"Leí «{title}» desde Drive. "
            + ask_scope_prompt()
        ),
        "pre_assist_done": True,
        "needs_approval": False,
        "approval_kind": None,
        "pending_google_tool": None,
    }


def _pre_assist_node(state: AgentState, db: Session) -> dict:
    """Cierra un guardado de contexto pendiente. Las acciones nuevas las decide el LLM."""
    message = state["user_message"]
    session_id = state["session_id"]
    user_id = state.get("user_id")

    if is_audit_retry(message):
        staged = get_retryable_staging(session_id, db=db)
        if staged:
            skill = skill_from_staging(staged)
            return {
                "pending_skill": skill,
                "skill_approved": True,
                "allow_network": bool(staged.get("network_granted")),
                "needs_approval": False,
                "approval_kind": None,
                "pre_assist_done": False,
                "retry_staged_audit": True,
                "reply": "",
                "pending_google_tool": None,
                "google_approved": None,
            }

    pending_note = get_pending_note(session_id)
    if pending_note:
        scope = parse_context_scope(message)
        if scope:
            clear_pending_note(session_id)
            reply = _save_scoped_note(
                db, content=pending_note, scope=scope, user_id=user_id
            )
            return {
                "reply": reply,
                "pre_assist_done": True,
                "needs_approval": False,
                "approval_kind": None,
                "pending_skill": None,
                "pending_google_tool": None,
            }
        if looks_like_save_context_intent(message):
            # Nuevo pedido reemplaza el pendiente.
            set_pending_note(session_id, extract_note_body(message))
            return {
                "reply": ask_scope_prompt(),
                "pre_assist_done": True,
                "needs_approval": False,
                "approval_kind": None,
                "pending_skill": None,
                "pending_google_tool": None,
            }
        # El usuario no contestó el alcance: siguió el chat. No hijackear.
        clear_pending_note(session_id)

    return {
        "pre_assist_done": False,
        "pending_google_tool": None,
        "google_approved": None,
    }


def _fetch_history_node(state: AgentState, db: Session) -> dict:
    rows = db.execute(
        text(
            """
            SELECT role, message
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        {"session_id": state["session_id"]},
    ).mappings().all()

    history = [
        {"role": row["role"], "message": row["message"]}
        for row in reversed(list(rows))
    ]
    return {
        "history": history,
        "thread_state": load_thread_state(db, state.get("session_id")),
    }


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


def _annotate_plan_result(
    result: dict[str, Any],
    parts: OrderParts,
    *,
    llm_reply: str = "",
) -> dict[str, Any]:
    """No se pierde horario ni recap, sin importar si es Google, skill o descarga."""
    out = dict(result)
    if parts.when_iso:
        out["run_at"] = parts.when_iso
        skill = out.get("pending_skill")
        if isinstance(skill, dict):
            out["pending_skill"] = {**skill, "run_at": parts.when_iso}
        pending = out.get("pending_google_tool")
        if isinstance(pending, dict):
            args = {
                **(pending.get("arguments") or {}),
                "send_at": parts.when_iso,
                "run_at": parts.when_iso,
            }
            out["pending_google_tool"] = {**pending, "arguments": args}
    ack = parts.commit_ack()
    if ack:
        out["order_ack"] = ack
    reply = (out.get("reply") or "").strip()
    setup = (llm_reply or "").strip()
    if out.get("needs_approval"):
        # HITL estricto: un solo mensaje = la tarjeta de autorización.
        # No mezclar prosa del LLM ni recaps largos en este turno.
        out["reply"] = ""
        return out
    chunks: list[str] = []
    if ack and ack.lower() not in reply.lower():
        chunks.append(ack)
    if reply:
        chunks.append(reply)
    elif setup and "no puedo" not in setup.lower():
        chunks.append(setup)
    if chunks:
        out["reply"] = "\n\n".join(chunks)
    return out


def _auto_execute_skill_state(skill: dict[str, Any]) -> dict[str, Any]:
    """Skill en whitelist: ejecutar sin HITL."""
    return {
        "pending_skill": skill,
        "approval_kind": None,
        "needs_approval": False,
        "skill_approved": True,
        "reply": "",
    }


def _conversation_text(state: AgentState) -> str:
    return conversation_context_text(
        state.get("user_message") or "",
        state.get("history") or [],
    )


def _apply_context_switch(
    thread_state: dict[str, Any],
    user_message: str,
    *,
    history: list[dict[str, Any]] | None = None,
    context_text: str | None = None,
) -> dict[str, Any]:
    """Si el mensaje es una solicitud nueva, reemplaza open_task y no arrastra la vieja."""
    if not is_context_switch(
        user_message,
        context_text=context_text,
        history=history,
        thread_state=thread_state,
    ):
        return thread_state
    new_task = (
        extract_open_task(user_message, history, user_message, thread_state=None)
        or (user_message or "").strip()[:300]
    )
    switched = dict(thread_state or {})
    switched["open_task"] = new_task
    summary = (
        dict(switched["summary_json"])
        if isinstance(switched.get("summary_json"), dict)
        else {}
    )
    summary["open_task"] = new_task
    summary["status"] = "in_progress"
    switched["summary_json"] = summary
    switched["summary_text"] = (
        "CAMBIO DE TAREA: el usuario dejó lo anterior. "
        f"Tarea actual: {new_task}"
    )
    return switched


def _force_skill_or_download(
    user_message: str,
    *,
    context_text: str | None = None,
    thread_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resuelve skill con criterio estricto; si duda, pregunta."""
    return _plan_from_decision(
        resolve_skill_decision(
            user_message,
            context_text=context_text,
            thread_state=thread_state,
        ),
        user_message=user_message,
        context_text=context_text,
    )


def _plan_from_decision(
    decision: dict[str, Any],
    *,
    user_message: str = "",
    context_text: str | None = None,
) -> dict[str, Any]:
    action = decision.get("action")
    if action == "clarify":
        return {
            "pending_skill": None,
            "needs_approval": False,
            "approval_kind": None,
            "reply": decision.get("reply")
            or "¿Me podés aclarar qué necesitás exactamente?",
        }
    if action == "execute":
        skill = decision.get("skill") or {}
        if not skill.get("found"):
            # Sin skill local: intentar reusar remota ya instalada antes de pedir descarga.
            reused = resolve_reusable_remote_skill(
                user_message or "",
                conversation_context=context_text,
            )
            if reused:
                return _auto_execute_skill_state(reused)
            return {
                "pending_skill": None,
                "approval_kind": APPROVAL_KIND_DOWNLOAD,
                "needs_approval": True,
                "reply": "",
            }
        if can_auto_reuse_skill(skill) or is_whitelisted(
            str(skill.get("id") or ""), str(skill.get("code") or "")
        ):
            return _auto_execute_skill_state(skill)
        return {
            "pending_skill": skill,
            "approval_kind": APPROVAL_KIND_EXECUTE,
            "needs_approval": True,
            "reply": "",
        }
    if action == "download":
        # Ya la ejecutamos / está en whitelist → no volver a pedir descarga.
        reused = resolve_reusable_remote_skill(
            user_message or "",
            conversation_context=context_text,
        )
        if reused:
            return _auto_execute_skill_state(reused)
        return {
            "pending_skill": None,
            "approval_kind": APPROVAL_KIND_DOWNLOAD,
            "needs_approval": True,
            "reply": "",
        }
    return {
        "pending_skill": None,
        "needs_approval": False,
        "approval_kind": None,
        "reply": "",
    }


def _resolve_skill_plan(
    task: str,
    arguments: dict[str, Any],
    user_message: str,
    *,
    context_text: str | None = None,
    thread_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Evalúa skills con matching endurecido + aclaraciones."""
    decision = resolve_skill_decision(
        user_message,
        arguments,
        context_text=context_text or user_message,
        thread_state=thread_state,
    )
    if decision.get("action") == "none":
        return None
    return _plan_from_decision(
        decision,
        user_message=user_message,
        context_text=context_text or user_message,
    )


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_call_args(call: Any) -> dict[str, Any]:
    raw = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
    return raw if isinstance(raw, dict) else {}


def _plan_save_context(state: AgentState, db: Session, args: dict[str, Any]) -> dict:
    note = str(args.get("note") or "").strip() or extract_note_body(
        state["user_message"]
    )
    scope = parse_context_scope(str(args.get("scope") or "")) or parse_context_scope(
        state["user_message"]
    )
    if not note:
        return {
            "pending_skill": None,
            "pending_google_tool": None,
            "needs_approval": False,
            "approval_kind": None,
            "reply": "¿Qué querés que anote como contexto?",
        }
    if scope:
        return {
            "pending_skill": None,
            "pending_google_tool": None,
            "needs_approval": False,
            "approval_kind": None,
            "reply": _save_scoped_note(
                db, content=note, scope=scope, user_id=state.get("user_id")
            ),
        }
    set_pending_note(state["session_id"], note)
    return {
        "pending_skill": None,
        "pending_google_tool": None,
        "needs_approval": False,
        "approval_kind": None,
        "reply": ask_scope_prompt(),
    }


def _plan_google_action(state: AgentState, db: Session, args: dict[str, Any]) -> dict:
    action = str(args.get("action") or "").strip()
    meta = GOOGLE_ACTIONS.get(action)
    empty = {
        "pending_skill": None,
        "pending_google_tool": None,
        "needs_approval": False,
        "approval_kind": None,
        "google_approved": None,
    }
    if not meta:
        return {
            **empty,
            "reply": (
                "No entendí si era un mail, un evento de Calendar o algo de Drive. "
                "Aclarámelo y lo hago."
            ),
        }
    user_id = state.get("user_id")
    if not user_id:
        return {
            **empty,
            "reply": (
                "Para usar Calendar, Gmail o Drive necesitás "
                "**iniciar sesión con Google** (botón en el menú)."
            ),
        }
    if not google_oauth_configured():
        return {
            **empty,
            "reply": "Google OAuth todavía no está configurado en el servidor.",
        }
    query = str(args.get("query") or state["user_message"])
    parts = extract_order_parts(state["user_message"], _conversation_text(state), query)
    pending = build_pending_google_tool(
        {"tool_id": meta["tool_id"], "action": action, "write": meta["write"]},
        query,
    )
    overlay = {
        key: args.get(key)
        for key in (
            "to",
            "subject",
            "body",
            "summary",
            "start_iso",
            "end_iso",
            "search",
            "file_id",
            "send_at",
            "run_at",
        )
        if args.get(key)
    }
    pending["arguments"] = merge_args_with_order(
        {**(pending.get("arguments") or {}), **overlay},
        parts,
    )
    pending["arguments"]["session_id"] = state.get("session_id")
    pending["arguments"]["query"] = query
    recap = parts.recap()
    ask = missing_google_slots(
        action,
        f"{query}\n{_conversation_text(state)}",
        pending.get("arguments"),
    )
    if ask:
        prefix = f"{recap}\n\n" if recap else ""
        return {**empty, "reply": prefix + ask}
    if pending.get("action") == "drive_index":
        result = _handle_drive_index_to_context(
            db,
            user_id=user_id,
            session_id=state["session_id"],
            pending=pending,
        )
        result["pending_skill"] = None
        return result
    if google_write_needs_hitl(db, user_id, pending):
        return {
            "pending_google_tool": pending,
            "needs_approval": True,
            "approval_kind": APPROVAL_KIND_GOOGLE_TOOL,
            "pending_skill": None,
            "reply": "",
        }
    try:
        reply = execute_google_tool(db, user_id=user_id, pending=pending)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo tool Google %s", pending.get("tool_id"))
        reply = f"No pude completar la acción de Google: {exc}"
    return {**empty, "reply": reply}


def _plan_native_google(state: AgentState, db: Session, args: dict[str, Any]) -> dict:
    action = str(args.get("action") or "").strip() or infer_google_action(
        str(args.get("query") or state["user_message"])
    )
    if not action:
        action = infer_google_action(_conversation_text(state)) or ""
    merged = {**args, "action": action, "query": args.get("query") or state["user_message"]}
    return _plan_google_action(state, db, merged)


def _plan_casual_chat(state: AgentState, parts: OrderParts) -> dict:
    """Charla sin tools ni catálogo: un compañero, no un ticket."""
    llm = _llm(tools=False, temperature=0.5)
    thread_state = _thread_state(state)
    history = state.get("history") or []
    last_assistant = ""
    for item in reversed(history):
        if (item.get("role") or "").lower() in {"assistant", "ai"}:
            last_assistant = (item.get("message") or "").strip()
            if last_assistant:
                break
    focus = [
        CASUAL_SYSTEM,
        VOICE_HINT,
        "Último mensaje del usuario (respondé a ESTO): "
        + (state.get("user_message") or "").strip()[:400],
    ]
    if last_assistant:
        focus.append(
            "Tu mensaje anterior (si te lo cuestionan, explicalo; no improvises): "
            + last_assistant[:280]
        )
    system = fit_system_prompt("\n".join(focus))
    user_text = fit_user_message(state["user_message"])
    history_msgs = _history_messages(history, thread_state)
    try:
        response = llm.invoke(
            [
                SystemMessage(content=system),
                *history_msgs,
                HumanMessage(content=user_text),
            ]
        )
        reply = (getattr(response, "content", None) or "").strip()
    except Exception:
        logger.exception("Fallo el chat casual")
        reply = ""
    if not reply:
        reply = "¡Hola! Todo bien, ¿y vos?"
    return _annotate_plan_result(
        {
            "pending_skill": None,
            "needs_approval": False,
            "approval_kind": None,
            "reply": reply,
        },
        parts,
    )


def _plan_node(state: AgentState, db: Session) -> dict:
    ctx = _conversation_text(state)
    history = state.get("history") or []
    thread_state = _apply_context_switch(
        _thread_state(state),
        state["user_message"],
        history=history,
        context_text=ctx,
    )
    switched = is_context_switch(
        state["user_message"],
        context_text=ctx,
        history=history,
        thread_state=_thread_state(state),
    )
    parts = extract_order_parts(state["user_message"], ctx)
    if is_casual_chat(
        state["user_message"],
        history=state.get("history") or [],
        context_text=ctx,
        thread_state=thread_state,
    ):
        return _plan_casual_chat(state, parts)
    llm = _llm(tools=True)
    if (
        not switched
        and is_asking_for_needed_data(state["user_message"])
        and open_task_from_state(thread_state)
    ):
        return _annotate_plan_result(
            {
                "pending_skill": None,
                "needs_approval": False,
                "approval_kind": None,
                "reply": ask_inputs_for_open_task(
                    ctx,
                    history=history,
                    thread_state=thread_state,
                ),
            },
            parts,
        )
    system = fit_system_prompt(SYSTEM_PROMPT_IRRIGACION)
    native = fit_system_prompt(VOICE_HINT + "\n" + NATIVE_TOOLS_HINT)
    open_task = extract_open_task(
        state["user_message"],
        history,
        ctx,
        thread_state=thread_state,
    )
    if switched and open_task:
        tooling = fit_system_prompt(
            SKILL_TOOLING_HINT
            + "\nCAMBIO DE TAREA (obligatorio): "
            + open_task[:400]
            + "\nAbandoná lo anterior. No pidas datos de la tarea vieja. "
            "Si no hay skill local, search_skill_marketplace / descarga."
        )
    elif open_task:
        tooling = fit_system_prompt(
            SKILL_TOOLING_HINT
            + "\nTAREA ABIERTA (obligatorio continuar, no cambies de tema): "
            + open_task[:400]
            + "\nNo ofrezcas el catálogo de riego ni otra skill salvo que ESA sea la tarea."
        )
    else:
        tooling = fit_system_prompt(SKILL_TOOLING_HINT + "\n" + CATALOG_HINT)
    rag = "Contexto documental recuperado (RAG):\n\n" + _context_block(
        state.get("retrieved_docs") or []
    )
    user_text = fit_user_message(state["user_message"])
    history_msgs = _history_messages(state.get("history") or [], thread_state)
    style_hint = fit_system_prompt(
        "Preferencia de formato para esta respuesta: "
        + detect_response_style(state["user_message"])
    )
    order_hint = fit_system_prompt(
        "Orden parseada (cumplí TODAS las partes; no tires ninguna): "
        + (parts.recap() or state["user_message"])
        + (f" Horario: {parts.when_label}." if parts.when_label else "")
    )
    thread_hint = fit_system_prompt(
        thread_brief_for_prompt(
            state["user_message"],
            state.get("history") or [],
            thread_state=thread_state,
        )
    )
    memory_hint = fit_system_prompt(str(thread_state.get("summary_text") or "").strip())

    packed = [
        ("system", system),
        ("native", native),
        ("tooling", tooling),
        ("order", order_hint),
        ("memory", memory_hint),
        ("rag", rag),
        ("style", style_hint),
        ("thread", thread_hint),
        ("user", user_text),
    ]
    (
        system,
        native,
        tooling,
        order_hint,
        memory_hint,
        rag,
        style_hint,
        thread_hint,
        user_text,
    ) = enforce_request_budget(packed)

    messages: list = [
        SystemMessage(content=system),
        SystemMessage(content=native),
        SystemMessage(content=tooling),
        SystemMessage(content=order_hint),
        SystemMessage(content=thread_hint),
        SystemMessage(content=memory_hint),
        SystemMessage(content=rag),
        SystemMessage(content=style_hint),
        *history_msgs,
        HumanMessage(content=user_text),
    ]
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        logger.exception("Fallo el plan LLM (posible límite de tokens)")
        if should_use_native_google(state["user_message"], ctx):
            return _annotate_plan_result(
                _plan_native_google(state, db, {"query": state["user_message"]}),
                parts,
            )
        resolved = _resolve_skill_plan(
            state["user_message"],
            {"query": state["user_message"]},
            state["user_message"],
            context_text=ctx,
            thread_state=thread_state,
        )
        if resolved:
            return _annotate_plan_result(resolved, parts)
        if looks_like_do_task(state["user_message"]):
            return _annotate_plan_result(
                _force_skill_or_download(
                    state["user_message"],
                    context_text=ctx,
                    thread_state=thread_state,
                ),
                parts,
            )
        return {
            "pending_skill": None,
            "needs_approval": False,
            "reply": (
                "No pude consultar al modelo ahora (límite de tokens o error de API). "
                f"Detalle: {exc}. Probá una consulta más corta o modo Rápido."
            ),
        }
    tool_calls = getattr(response, "tool_calls", None) or []
    google_call = next(
        (call for call in tool_calls if _tool_call_name(call) == "use_google"),
        None,
    )
    save_call = next(
        (call for call in tool_calls if _tool_call_name(call) == "save_user_context"),
        None,
    )
    if is_result_challenge_or_correction(state["user_message"]) and (
        google_call
        or should_use_native_google(state["user_message"], ctx, tool_called=False)
    ):
        reply = (getattr(response, "content", None) or "").strip() or (
            "Tenés razón. Si el mail ya salió, no lo deshago. "
            "Si pedís un horario, lo programo y no lo mando al toque."
        )
        return _annotate_plan_result(
            {
                "pending_skill": None,
                "pending_google_tool": None,
                "needs_approval": False,
                "approval_kind": None,
                "reply": reply,
            },
            parts,
        )
    if should_use_native_google(
        state["user_message"],
        ctx,
        tool_called=bool(google_call),
    ):
        args = _tool_call_args(google_call) if google_call else {}
        return _annotate_plan_result(
            _plan_native_google(state, db, args),
            parts,
        )
    if save_call and looks_like_save_context_intent(state["user_message"]):
        return _annotate_plan_result(
            _plan_save_context(state, db, _tool_call_args(save_call)),
            parts,
        )

    for call in tool_calls:
        if _tool_call_name(call) != "search_skill_marketplace":
            continue
        raw_args = _tool_call_args(call)
        task, arguments = _parse_tool_arguments(raw_args or {}, state["user_message"])
        # Pedido nuevo: no mezclar con el hilo viejo. Si no, enriquecer task pobre.
        if switched:
            task = state["user_message"]
            arguments = {**arguments, "query": state["user_message"]}
        elif ctx and (not task or len(task) < 40 or task == state["user_message"]):
            task = ctx
            arguments = {**arguments, "query": ctx}
        resolved = _resolve_skill_plan(
            task,
            arguments,
            state["user_message"],
            context_text=ctx,
            thread_state=thread_state,
        )
        llm_bits = (getattr(response, "content", None) or "").strip()
        if resolved:
            return _annotate_plan_result(resolved, parts, llm_reply=llm_bits)
        # Re-evaluar con el mensaje completo (el task del tool a veces es pobre).
        forced = _force_skill_or_download(
            state["user_message"],
            context_text=ctx,
            thread_state=thread_state,
        )
        if (
            forced.get("reply")
            or forced.get("needs_approval")
            or forced.get("pending_skill")
        ):
            return _annotate_plan_result(forced, parts, llm_reply=llm_bits)
        available = ", ".join(
            s["name"] for s in search_catalog(task, arguments).get("available") or []
        )
        return _annotate_plan_result(
            {
                "pending_skill": None,
                "needs_approval": False,
                "reply": (
                    "No encontré una skill en el catálogo para esa tarea. "
                    f"Disponibles: {available or '(ninguna)'}. "
                    "¿Me aclarás qué resultado querés y con qué datos?"
                ),
            },
            parts,
            llm_reply=llm_bits,
        )

    reply = (getattr(response, "content", None) or "").strip()

    # Réplica al hilo (corrección/cuestionamiento): no forzar marketplace ni re-preguntar.
    if is_result_challenge_or_correction(state["user_message"]):
        if not reply:
            reply = (
                "Tenés razón en cuestionarlo: si el valor no calza con lo que ves en la "
                "página/API, decime y lo reconsultamos con la skill de telemetría "
                "(API fullDto) usando el mismo punto/URL del hilo."
            )
        return _annotate_plan_result(
            {
                "pending_skill": None,
                "needs_approval": False,
                "reply": reply,
            },
            parts,
        )

    # Hacer algo en el mundo / web / skill / "no puedo" → marketplace o descarga.
    if (
        looks_like_do_task(state["user_message"])
        or looks_like_skill_intent(state["user_message"])
        or looks_like_web_or_external_request(state["user_message"])
        or reply_is_capability_refusal(reply)
    ):
        return _annotate_plan_result(
            _force_skill_or_download(
                state["user_message"],
                context_text=ctx,
                thread_state=thread_state,
            ),
            parts,
            llm_reply=reply,
        )

    if not reply:
        reply = (
            "No pude generar una respuesta a partir del contexto disponible. "
            "Verificá que haya documentos indexados o reformulá la consulta."
        )
    return _annotate_plan_result(
        {
            "pending_skill": None,
            "needs_approval": False,
            "reply": reply,
        },
        parts,
    )


def _route_after_plan(
    state: AgentState,
) -> Literal[
    "run_skill",
    "human_gate_download",
    "human_gate_execute",
    "human_gate_google",
    "end_ok",
]:
    if (
        state.get("approval_kind") == APPROVAL_KIND_GOOGLE_TOOL
        and state.get("needs_approval")
        and state.get("pending_google_tool")
    ):
        return "human_gate_google"
    if (
        state.get("skill_approved")
        and state.get("pending_skill")
        and not state.get("needs_approval")
    ):
        return "run_skill"
    kind = state.get("approval_kind")
    if kind == APPROVAL_KIND_DOWNLOAD:
        return "human_gate_download"
    if kind == APPROVAL_KIND_EXECUTE and state.get("pending_skill"):
        return "human_gate_execute"
    return "end_ok"


def _route_after_pre_assist(
    state: AgentState,
) -> Literal["human_gate_google", "plan", "run_skill", "end_ok"]:
    if (
        state.get("approval_kind") == APPROVAL_KIND_GOOGLE_TOOL
        and state.get("needs_approval")
        and state.get("pending_google_tool")
    ):
        return "human_gate_google"
    if (
        state.get("retry_staged_audit")
        and state.get("skill_approved")
        and state.get("pending_skill")
    ):
        return "run_skill"
    if state.get("pre_assist_done"):
        return "end_ok"
    return "plan"


def _approval_prompt(skill: dict[str, Any]) -> str:
    name = skill.get("name") or "desconocida"
    source = skill.get("source")
    if source == "remote":
        return (
            f"Ya tengo lista la skill '{name}' (descargada). "
            "¿Autorizás a Gemini a auditarla y ejecutarla?"
        )
    return (
        f"Encontré la skill '{name}' en el catálogo. "
        "¿Autorizás a Gemini a auditarla y ejecutarla?"
        " Si pediste un horario, la corro a esa hora (no ahora)."
    )


def _google_tool_prompt(pending: dict[str, Any]) -> str:
    tool_id = pending.get("tool_id") or pending.get("name") or "google"
    args = pending.get("arguments") or {}
    parts = extract_order_parts(str(args.get("query") or ""), str(args.get("body") or ""))
    recap = parts.recap()
    extra = f" {recap}" if recap else ""
    if tool_id == "calendar.create":
        return (
            f"Voy a crear el evento **{args.get('summary') or 'sin título'}** "
            f"({args.get('start_iso')} → {args.get('end_iso')}) en tu Calendar. "
            f"{extra} ¿Autorizás?"
        )
    if tool_id == "gmail.send":
        when = args.get("send_at") or args.get("run_at") or parts.when_iso
        dest = args.get("to") or parts.to or "(sin destinatario)"
        subject = args.get("subject") or parts.subject or ""
        if when or parts.when_label:
            label = parts.when_label or str(when)
            try:
                from datetime import datetime

                label = datetime.fromisoformat(str(when)).astimezone().strftime("%H:%M")
            except (TypeError, ValueError):
                pass
            return (
                f"Voy a **programar** un mail a **{dest}** "
                f"con asunto «{subject}» para **{label}** "
                f"(no sale ahora).{extra} ¿Autorizás?"
            )
        return (
            f"Voy a enviar un mail a **{dest}** "
            f"con asunto «{subject}».{extra} ¿Autorizás?"
        )
    return f"Voy a ejecutar **{tool_id}** en tu cuenta Google.{extra} ¿Autorizás?"


def _interrupt_to_prompt(payload: dict[str, Any], values: dict[str, Any]) -> str:
    kind = payload.get("approval_kind") or payload.get("intent")
    # HITL estricto: únicamente el texto de autorización (sin prosa del plan).
    if kind == APPROVAL_KIND_DOWNLOAD:
        return download_remote_prompt()
    if kind == APPROVAL_KIND_GOOGLE_TOOL:
        pending = values.get("pending_google_tool") or {}
        return _google_tool_prompt(pending)
    if kind == APPROVAL_KIND_NETWORK:
        label = payload.get("capability_label") or "Cliente HTTP/Socket"
        return network_permission_prompt(str(label))
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
    ctx = _conversation_text(state)
    # Si ya está instalada/auditada, ni siquiera "descargar": ejecutar directo.
    reused = resolve_reusable_remote_skill(
        state["user_message"],
        conversation_context=ctx,
    )
    if reused:
        return _auto_execute_skill_state(reused)
    try:
        skill = generate_remote_skill(
            state["user_message"],
            rag_context=_context_block(state.get("retrieved_docs") or []),
            conversation_context=ctx,
        )
        # Segunda red de seguridad: nunca ofrecer HITL sobre skills meta.
        validate_remote_skill(skill, ctx or state["user_message"])
    except Exception as exc:
        logger.exception("Fallo al descargar skill remota")
        return {
            "reply": (
                f"No pude preparar una skill válida: {exc}\n\n"
                "Decime de nuevo el dato concreto, la URL/API y el punto "
                "(ej. altura del 10009 en telemetría)."
            ),
            "needs_approval": False,
            "approval_kind": None,
        }
    if can_auto_reuse_skill(skill) or is_whitelisted(
        str(skill.get("id") or ""), str(skill.get("code") or "")
    ):
        return _auto_execute_skill_state(skill)
    # El usuario ya autorizó "descargar y ejecutar" en human_gate_download.
    # No pedir un segundo HITL: auditar + sandbox en este mismo resume.
    upsert_skill_staging(
        session_id=str(state.get("session_id") or ""),
        skill=skill,
        status=STATUS_DOWNLOADED,
        user_id=state.get("user_id"),
    )
    return {
        "pending_skill": skill,
        "approval_kind": None,
        "needs_approval": False,
        "skill_approved": True,
        "reply": "",
    }


def _route_after_fetch(
    state: AgentState,
) -> Literal["run_skill", "human_gate_execute", "end_ok"]:
    if (
        state.get("skill_approved")
        and state.get("pending_skill")
        and not state.get("needs_approval")
    ):
        return "run_skill"
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
    return {
        "skill_approved": approved,
        "needs_approval": False,
        "approval_kind": None,
    }


def _human_gate_google_node(state: AgentState) -> dict:
    pending = state.get("pending_google_tool") or {}
    decision = interrupt(
        {
            "intent": APPROVAL_KIND_GOOGLE_TOOL,
            "approval_kind": APPROVAL_KIND_GOOGLE_TOOL,
            "skill_name": pending.get("name") or pending.get("tool_id"),
            "skill_description": pending.get("description"),
            "tool_id": pending.get("tool_id"),
        }
    )
    if isinstance(decision, dict):
        approved = bool(decision.get("approved"))
    else:
        approved = bool(decision)
    return {
        "google_approved": approved,
        "needs_approval": False,
        "approval_kind": None,
    }


def _stage_pending_skill(
    state: AgentState,
    skill: dict[str, Any],
    status: str,
    *,
    needs_network: bool | None = None,
    network_granted: bool | None = None,
    last_error: str | None = None,
    audit: dict[str, Any] | None = None,
) -> None:
    upsert_skill_staging(
        session_id=str(state.get("session_id") or ""),
        skill=skill,
        status=status,
        user_id=state.get("user_id"),
        needs_network=needs_network,
        network_granted=network_granted,
        last_error=last_error,
        audit=audit,
    )


def _audit_gate_from_result(
    state: AgentState,
    skill: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    status = result.get("status")
    audit = result.get("audit") or {}
    if status == "audit_unavailable":
        _stage_pending_skill(
            state,
            skill,
            STATUS_PENDING_AUDIT,
            needs_network=bool(audit.get("needs_network")),
            last_error=str(audit.get("reason") or ""),
            audit=audit,
        )
        return {
            "skill_result": result,
            "reply": AUDIT_RETRY_PROMPT,
            "pending_skill": skill,
            "needs_approval": False,
            "approval_kind": None,
            "retry_staged_audit": False,
        }
    if status == "needs_network":
        _stage_pending_skill(
            state,
            skill,
            STATUS_REQUIRES_PERMISSION,
            needs_network=True,
            network_granted=False,
            audit=audit,
        )
        return {
            "skill_result": result,
            "reply": "",
            "pending_skill": skill,
            "needs_approval": True,
            "approval_kind": APPROVAL_KIND_NETWORK,
            "allow_network": False,
        }
    if status == "rejected":
        _stage_pending_skill(
            state,
            skill,
            STATUS_FAILED,
            last_error=str(audit.get("reason") or ""),
            audit=audit,
        )
        return {
            "skill_result": result,
            "reply": "",
            "pending_skill": skill,
            "needs_approval": False,
            "approval_kind": None,
        }
    return None


def _human_gate_network_node(state: AgentState) -> dict:
    skill = state.get("pending_skill") or {}
    audit = (state.get("skill_result") or {}).get("audit") or {}
    labels = audit.get("network_capabilities") or ["Cliente HTTP/Socket"]
    label = labels[0] if isinstance(labels, list) and labels else "Cliente HTTP/Socket"
    decision = interrupt(
        {
            "intent": APPROVAL_KIND_NETWORK,
            "approval_kind": APPROVAL_KIND_NETWORK,
            "skill_id": skill.get("id"),
            "skill_name": skill.get("name"),
            "skill_description": skill.get("description"),
            "capability_label": label,
        }
    )
    approved = (
        bool(decision.get("approved"))
        if isinstance(decision, dict)
        else bool(decision)
    )
    if not approved:
        _stage_pending_skill(
            state,
            skill if isinstance(skill, dict) else {},
            STATUS_FAILED,
            network_granted=False,
            last_error="Permiso de red cancelado por el usuario",
        )
        return {
            "skill_approved": False,
            "allow_network": False,
            "needs_approval": False,
            "approval_kind": None,
            "reply": (
                "Entendido. No autorizaste el permiso de red; cancelé la skill."
            ),
        }
    _stage_pending_skill(
        state,
        skill if isinstance(skill, dict) else {},
        STATUS_REQUIRES_PERMISSION,
        needs_network=True,
        network_granted=True,
    )
    return {
        "skill_approved": True,
        "allow_network": True,
        "needs_approval": False,
        "approval_kind": None,
        "reply": "",
    }


def _route_after_network_gate(
    state: AgentState,
) -> Literal["run_skill", "end_ok"]:
    if state.get("allow_network") and state.get("skill_approved"):
        return "run_skill"
    return "end_ok"


def _route_after_run_skill(
    state: AgentState,
) -> Literal["human_gate_network", "compose_skill_reply"]:
    if (
        state.get("needs_approval")
        and state.get("approval_kind") == APPROVAL_KIND_NETWORK
        and state.get("pending_skill")
    ):
        return "human_gate_network"
    return "compose_skill_reply"


def _run_google_tool_node(state: AgentState, db: Session) -> dict:
    if not state.get("google_approved"):
        return {
            "reply": "Entendido. Cancelé la acción de Google.",
            "pending_google_tool": None,
            "google_approved": False,
        }
    user_id = state.get("user_id")
    pending = state.get("pending_google_tool") or {}
    if not user_id:
        return {
            "reply": "Necesitás iniciar sesión con Google para continuar.",
            "pending_google_tool": None,
        }
    try:
        reply = execute_google_tool(db, user_id=user_id, pending=pending)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo tool Google post-HITL")
        reply = f"No pude completar la acción de Google: {exc}"
    return {
        "reply": reply,
        "pending_google_tool": None,
        "google_approved": True,
    }


def _run_skill_node(state: AgentState, db: Session) -> dict:
    if not state.get("skill_approved"):
        return {
            "skill_result": None,
            "reply": (
                "Entendido. No instalé ni ejecuté la skill porque cancelaste "
                "la autorización."
            ),
        }

    skill = dict(state.get("pending_skill") or {})
    ctx = _conversation_text(state)
    skill["arguments"] = prepare_skill_arguments(
        skill,
        state["user_message"],
        context_text=ctx,
    )
    args = dict(skill.get("arguments") or {})
    # Siempre pasar el pedido como query; skills zero-arg lo usan o lo ignoran.
    if not args.get("query"):
        args["query"] = state.get("user_message") or ""
        skill["arguments"] = args

    missing = skill_missing_required_inputs(
        skill,
        args,
        context_text=ctx,
        user_message=state.get("user_message") or "",
    )
    if missing:
        return {
            "skill_result": None,
            "reply": clarifying_question_for_skill(skill, missing),
            "pending_skill": None,
            "needs_approval": False,
            "approval_kind": None,
        }
    try:
        validate_remote_skill(skill, ctx or state["user_message"])
    except Exception as exc:
        logger.exception("Skill pendiente inválida bloqueada antes de ejecutar")
        return {
            "skill_result": None,
            "reply": (
                f"Aborté la ejecución: la skill no es válida ({exc}). "
                "Pedime de nuevo el dato + URL/punto y generamos una skill real."
            ),
            "pending_skill": None,
            "needs_approval": False,
            "approval_kind": None,
        }
    if not state.get("retry_staged_audit"):
        _stage_pending_skill(state, skill, STATUS_DOWNLOADED)
    code = skill.get("code") or ""
    arguments = skill.get("arguments") or {}
    allow_network = bool(state.get("allow_network"))
    parts = extract_order_parts(state.get("user_message") or "", ctx)
    when_iso = parts.when_iso or state.get("run_at")
    if when_iso:
        from datetime import datetime

        from app.services.scheduled_jobs import enqueue_job

        prepared = evaluate_skill_audit_sync(
            code,
            skill_id=str(skill.get("id") or "") or None,
            skill_name=str(skill.get("name") or "") or None,
            source=str(skill.get("source") or "local") or None,
            allow_network=allow_network,
        )
        gated = _audit_gate_from_result(state, skill, prepared)
        if gated:
            return gated
        try:
            when = datetime.fromisoformat(str(when_iso))
            enqueue_job(
                db,
                user_id=state.get("user_id"),
                session_id=str(state.get("session_id") or "") or None,
                kind="skill_execute",
                payload={
                    "skill": {
                        "id": skill.get("id"),
                        "name": skill.get("name"),
                        "code": skill.get("code"),
                        "source": skill.get("source"),
                        "arguments": skill.get("arguments"),
                    },
                    "user_message": state.get("user_message"),
                    "context": ctx,
                    "allow_network": allow_network
                    or bool(prepared.get("allow_network")),
                },
                run_at=when,
            )
            recap = parts.recap()
            label = parts.when_label or "el horario pedido"
            _stage_pending_skill(
                state,
                skill,
                STATUS_APPROVED,
                network_granted=allow_network
                or bool(prepared.get("allow_network")),
            )
            return {
                "skill_result": None,
                "reply": (
                    f"{recap}\n\nQuedó **programado** para **{label}**. "
                    "No lo hago ahora; a esa hora lo ejecuto y te dejo el resultado acá."
                ),
                "pending_skill": None,
            }
        except Exception:
            logger.exception("No pude programar la skill; la ejecuto ahora")
    try:
        result = execute_skill_sync(
            code,
            arguments,
            skill_id=str(skill.get("id") or "") or None,
            skill_name=str(skill.get("name") or "") or None,
            source=str(skill.get("source") or "local") or None,
            allow_network=allow_network,
        )
    except Exception as exc:
        logger.exception("Fallo al ejecutar skill")
        name = skill.get("name") or "skill"
        mode = get_settings().skill_execution_mode
        hint = (
            "Si usás sandbox y falta la imagen, en el servidor corré: "
            "docker build -t skill-sandbox-image backend/sandbox_env"
            if mode == "sandbox"
            else "Revisá el código de la skill o cambiá SKILL_EXECUTION_MODE."
        )
        _stage_pending_skill(
            state,
            skill,
            STATUS_FAILED,
            last_error=str(exc),
        )
        return {
            "skill_result": {
                "status": "error",
                "audit": None,
                "execution": {"error": str(exc)},
            },
            "reply": f"No pude ejecutar la skill '{name}': {exc}. {hint}",
            "pending_skill": skill,
        }
    gated = _audit_gate_from_result(state, skill, result)
    if gated:
        return gated
    if result.get("status") == "executed":
        _stage_pending_skill(
            state,
            skill,
            STATUS_APPROVED,
            network_granted=allow_network,
        )
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


def _sanitize_for_llm(value: Any, *, depth: int = 0) -> Any:
    return sanitize_json_for_llm(value, depth=depth)


def _compose_skill_reply_node(state: AgentState) -> dict:
    if state.get("reply"):
        return {}

    result = state.get("skill_result") or {}
    skill = state.get("pending_skill") or {}
    name = skill.get("name") or "skill"
    user_message = state.get("user_message") or ""

    if result.get("status") == "rejected":
        audit = result.get("audit") or {}
        if audit.get("audit_unavailable"):
            return {"reply": AUDIT_RETRY_PROMPT}
        reason = audit.get("reason") or "riesgo detectado"
        return {
            "reply": (
                f"No pude usar esa automatización: la auditoría de seguridad la frenó "
                f"({reason})."
            )
        }

    if result.get("status") == "audit_unavailable":
        return {"reply": AUDIT_RETRY_PROMPT}

    if result.get("status") == "needs_network":
        audit = result.get("audit") or {}
        labels = audit.get("network_capabilities") or ["Cliente HTTP/Socket"]
        label = labels[0] if isinstance(labels, list) and labels else "Cliente HTTP/Socket"
        return {"reply": network_permission_prompt(str(label))}

    if result.get("status") == "error":
        execution = result.get("execution") or {}
        err = str(execution.get("error") or "error desconocido")
        if re.search(
            r"datos|data|falt|proporcion|argument|required|missing",
            err,
            re.I,
        ):
            skill = state.get("pending_skill") or {}
            missing = skill_missing_required_inputs(
                skill if isinstance(skill, dict) else {},
                (skill.get("arguments") if isinstance(skill, dict) else {}) or {},
                context_text=_conversation_text(state),
                user_message=user_message,
            )
            if missing:
                return {
                    "reply": clarifying_question_for_skill(
                        skill if isinstance(skill, dict) else {},
                        missing,
                    )
                }
            return {
                "reply": (
                    f"La skill pidió un dato concreto: {err}. "
                    "Pasámelo y la reintento."
                )
            }
        return {
            "reply": (
                f"No pude completar esa consulta: {err}. "
                "Si hace falta, reformulá el pedido o pedime otro dato."
            )
        }

    execution = result.get("execution") or {}
    skill_data = _skill_result_payload(execution)
    attachments = _persist_skill_attachments(skill_data)

    parsed = execution.get("parsed")
    raw_payload = parsed if parsed is not None else execution
    sanitized = sanitize_json_for_llm(raw_payload)
    payload = dumps_capped(sanitized, max_tokens=token_budget()["skill_result_max"])
    style = detect_response_style(user_message)

    human = humanize_skill_payload(
        user_message=user_message,
        skill_name=str(name),
        skill_data=skill_data,
        sanitized_payload=sanitized,
        attachments=attachments,
    )

    reply = ""
    try:
        llm = _llm(tools=False)
        if attachments:
            response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "Sos un colega de la oficina de Irrigación de Malargüe. "
                            "Confirmá en 1-3 frases que generaste el archivo, con lenguaje "
                            "humano y directo. Sin JSON ni jerga técnica. "
                            f"Estilo: {style}"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Pedido: {fit_user_message(user_message)}\n"
                            f"Archivos: {', '.join(a['filename'] for a in attachments)}\n"
                            f"Meta: {dumps_capped(sanitize_json_for_llm(skill_data or {}), max_tokens=400)}"
                        )
                    ),
                ]
            )
        else:
            response = llm.invoke(
                [
                    SystemMessage(content=llm_skill_narration_prompt(style)),
                    HumanMessage(
                        content=(
                            f"Pedido del usuario: {fit_user_message(user_message)}\n"
                            f"Datos obtenidos (JSON interno, NO lo copies):\n{payload}\n\n"
                            "Respondé al usuario con el dato masticado."
                        )
                    ),
                ]
            )
        reply = (getattr(response, "content", None) or "").strip()
    except Exception:
        logger.exception("Fallo al narrar resultado de skill con LLM; uso normalización")

    reply = normalize_assistant_reply(
        reply,
        user_message=user_message,
        skill_name=str(name),
        skill_data=skill_data,
        sanitized_payload=sanitized,
        attachments=attachments,
    )
    if not reply:
        reply = fallback_skill_reply(
            name=str(name),
            user_message=user_message,
            skill_data=skill_data,
            sanitized_payload=sanitized,
            attachments=attachments,
        )

    # Tipos conocidos: plantilla humana determinística (dato masticado, siempre igual).
    data = skill_data if isinstance(skill_data, dict) else unwrap_result(sanitized)
    kind = classify_skill_payload(data) if isinstance(data, dict) else "generico"
    if human and (kind != "generico" or looks_raw_technical(reply)):
        reply = human
    return {"reply": reply, "attachments": attachments}


def _finalize_user_facing_reply(
    reply: str,
    *,
    user_message: str = "",
    values: dict[str, Any] | None = None,
) -> str:
    """Última red de normalización antes de persistir/devolver al usuario."""
    values = values or {}
    skill = values.get("pending_skill") or {}
    skill_result = values.get("skill_result") or {}
    execution = (
        skill_result.get("execution") if isinstance(skill_result, dict) else None
    ) or {}
    parsed = execution.get("parsed") if isinstance(execution, dict) else None
    sanitized = sanitize_json_for_llm(parsed if parsed is not None else execution)
    skill_data = None
    if isinstance(parsed, dict):
        inner = parsed.get("result")
        skill_data = inner if isinstance(inner, dict) else parsed
    return normalize_assistant_reply(
        reply,
        user_message=user_message or values.get("user_message") or "",
        skill_name=str(skill.get("name") or ""),
        skill_data=skill_data,
        sanitized_payload=sanitized,
        attachments=values.get("attachments") or [],
    )


def _persist_message(
    db: Session,
    session_id: str,
    role: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chat_messages (session_id, user_id, role, message, metadata)
            VALUES (
                :session_id,
                CAST(:user_id AS uuid),
                :role,
                :message,
                CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "message": message,
            "metadata": json.dumps(metadata, ensure_ascii=False) if metadata else None,
        },
    )
    db.commit()


def extract_interrupt_payload(snapshot: Any) -> dict[str, Any] | None:
    """Solo interrupciones reales de LangGraph.

    No inferir HITL desde values (needs_approval/pending_skill): esos flags
    quedan en el checkpoint tras autorizar/cancelar y provocaban un bucle
    eterno de cards de Autorizar/Cancelar.
    """
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
    return None


def build_agent_graph(db: Session):
    graph = StateGraph(AgentState)

    def retrieve(state: AgentState) -> dict:
        return _retrieve_node(state, db)

    def fetch_history(state: AgentState) -> dict:
        return _fetch_history_node(state, db)

    def pre_assist(state: AgentState) -> dict:
        return _pre_assist_node(state, db)

    def run_google(state: AgentState) -> dict:
        return _run_google_tool_node(state, db)

    def plan(state: AgentState) -> dict:
        return _plan_node(state, db)

    def run_skill(state: AgentState) -> dict:
        return _run_skill_node(state, db)

    graph.add_node("retrieve", retrieve)
    graph.add_node("fetch_history", fetch_history)
    graph.add_node("pre_assist", pre_assist)
    graph.add_node("plan", plan)
    graph.add_node("human_gate_download", _human_gate_download_node)
    graph.add_node("fetch_remote_skill", _fetch_remote_skill_node)
    graph.add_node("human_gate_execute", _human_gate_execute_node)
    graph.add_node("human_gate_google", _human_gate_google_node)
    graph.add_node("human_gate_network", _human_gate_network_node)
    graph.add_node("run_google", run_google)
    graph.add_node("run_skill", run_skill)
    graph.add_node("compose_skill_reply", _compose_skill_reply_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "fetch_history")
    graph.add_edge("fetch_history", "pre_assist")
    graph.add_conditional_edges(
        "pre_assist",
        _route_after_pre_assist,
        {
            "human_gate_google": "human_gate_google",
            "plan": "plan",
            "run_skill": "run_skill",
            "end_ok": END,
        },
    )
    graph.add_conditional_edges(
        "plan",
        _route_after_plan,
        {
            "run_skill": "run_skill",
            "human_gate_download": "human_gate_download",
            "human_gate_execute": "human_gate_execute",
            "human_gate_google": "human_gate_google",
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
        {
            "run_skill": "run_skill",
            "human_gate_execute": "human_gate_execute",
            "end_ok": END,
        },
    )
    graph.add_edge("human_gate_execute", "run_skill")
    graph.add_edge("human_gate_google", "run_google")
    graph.add_edge("run_google", END)
    graph.add_conditional_edges(
        "run_skill",
        _route_after_run_skill,
        {
            "human_gate_network": "human_gate_network",
            "compose_skill_reply": "compose_skill_reply",
        },
    )
    graph.add_conditional_edges(
        "human_gate_network",
        _route_after_network_gate,
        {"run_skill": "run_skill", "end_ok": END},
    )
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
    user_id: str | None = None,
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
        name, description = _approval_display_names(kind, pending, values)
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name,
            skill_description=description,
            approval_kind=kind,
        )

    try:
        compiled.invoke(
            {
                "session_id": sid,
                "user_message": user_message,
                "speed_mode": resolved_speed_mode,
                "user_id": user_id,
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
                "pending_google_tool": None,
                "google_approved": None,
                "pre_assist_done": False,
                "run_at": None,
                "order_ack": None,
                "thread_state": {},
                "allow_network": False,
                "retry_staged_audit": False,
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
        kind = interrupt_payload.get("approval_kind")
        prompt = _interrupt_to_prompt(interrupt_payload, values)
        name, description = _approval_display_names(kind, interrupt_payload, values)
        _persist_message(db, sid, "user", user_message, user_id=user_id)
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
            user_id=user_id,
        )
        schedule_refresh(sid)
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name,
            skill_description=description,
            approval_kind=kind,
        )

    reply = _finalize_user_facing_reply(
        values.get("reply") or "",
        user_message=user_message,
        values=values,
    )
    attachments = values.get("attachments") or []
    embedding = values.get("query_embedding") or []
    _persist_message(db, sid, "user", user_message, user_id=user_id)
    assistant_meta: dict[str, Any] | None = None
    if attachments:
        assistant_meta = {"attachments": attachments}
    _persist_message(db, sid, "assistant", reply, assistant_meta, user_id=user_id)
    schedule_refresh(sid)
    if (
        embedding
        and not values.get("pre_assist_done")
        and cacheable_exchange(user_message, reply)
    ):
        save_to_semantic_cache(db, user_message, embedding, reply)
    return AgentOutcome(status=STATUS_OK, reply=reply, attachments=attachments or None)


def _approval_display_names(
    kind: str | None,
    payload: dict[str, Any],
    values: dict[str, Any],
) -> tuple[str | None, str | None]:
    if kind == APPROVAL_KIND_GOOGLE_TOOL:
        pending = values.get("pending_google_tool") or {}
        return (
            payload.get("skill_name") or pending.get("name") or pending.get("tool_id"),
            payload.get("skill_description") or pending.get("description"),
        )
    if kind == APPROVAL_KIND_EXECUTE:
        skill = values.get("pending_skill") or {}
        return (
            payload.get("skill_name") or skill.get("name"),
            payload.get("skill_description") or skill.get("description"),
        )
    if kind == APPROVAL_KIND_NETWORK:
        skill = values.get("pending_skill") or {}
        return (
            payload.get("skill_name") or skill.get("name"),
            payload.get("skill_description") or skill.get("description"),
        )
    return None, None


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
        name, description = _approval_display_names(kind, interrupt_payload, values)
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
        schedule_refresh(sid)
        return AgentOutcome(
            status=STATUS_APPROVAL,
            reply=prompt,
            skill_name=name,
            skill_description=description,
            approval_kind=kind,
        )

    reply = _finalize_user_facing_reply(
        values.get("reply") or "",
        user_message=values.get("user_message") or "",
        values=values,
    )
    attachments = values.get("attachments") or []
    skill_result = values.get("skill_result") or {}
    audit = (skill_result or {}).get("audit") if isinstance(skill_result, dict) else None
    user_message = values.get("user_message") or ""
    embedding = values.get("query_embedding") or []
    kind = pending.get("approval_kind")

    meta: dict[str, Any] = {
        "kind": "skill_result" if approved else "skill_denied",
        "approved": approved,
        "audit": audit,
    }
    if kind == APPROVAL_KIND_GOOGLE_TOOL:
        meta["kind"] = "google_tool_result" if approved else "google_tool_denied"
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
        schedule_refresh(sid)
    if approved and embedding and reply and kind != APPROVAL_KIND_GOOGLE_TOOL:
        save_to_semantic_cache(db, user_message, embedding, reply)

    name, description = _approval_display_names(kind, pending, values)
    return AgentOutcome(
        status="executed" if approved else "denied",
        reply=reply,
        skill_name=name,
        skill_description=description,
        audit=audit,
        attachments=attachments or None,
        approval_kind=None,
    )
