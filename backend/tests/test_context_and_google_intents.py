"""Tests mínimos de intents de contexto tipado y Google tools."""

from app.services.command_router import heuristic_route, resolve_command_intent
from app.services.context_memory import (
    extract_note_body,
    looks_like_save_context_intent,
    parse_context_scope,
)
from app.services.google_assistant import detect_google_intent


def test_save_context_intent_variants():
    assert looks_like_save_context_intent("Guardá esto como contexto: el canal 12 abre a las 8")
    assert looks_like_save_context_intent("anotá esto, es importante")
    assert looks_like_save_context_intent("recordá que mañana hay corte")
    assert not looks_like_save_context_intent("qué altura tiene el punto 10009")
    assert not looks_like_save_context_intent("Que onda crack! Como andas bld")
    assert not looks_like_save_context_intent("cómo andás")
    assert not looks_like_save_context_intent("todo bien?")
    assert not looks_like_save_context_intent("qué datos necesitás?")


def test_casual_chat_no_es_trabajo():
    from app.services.skill_marketplace import is_casual_chat

    assert is_casual_chat("Que onda crack! Como estas?")
    assert is_casual_chat("cómo andás")
    assert is_casual_chat("todo bien bld")
    assert not is_casual_chat("podés hacer un análisis de red?")
    assert not is_casual_chat("qué altura tiene el punto 10009")
    assert not is_casual_chat("recordá que mañana hay corte")
    assert not is_casual_chat("programame un mail a ana@x.com")


def test_charla_y_prompts_hitl_no_van_al_cache():
    from app.services.cache import (
        cacheable_exchange,
        is_reusable_knowledge_reply,
        should_use_semantic_cache,
    )
    from app.services.context_memory import ask_scope_prompt

    assert not should_use_semantic_cache("Que onda crack! Como andas bld?")
    assert not should_use_semantic_cache("cómo andás")
    assert not cacheable_exchange("Que onda crack! Como andas bld?", "Todo bien")
    assert should_use_semantic_cache("qué altura tiene el punto 10009")
    assert cacheable_exchange(
        "qué altura tiene el punto 10009",
        "El punto 10009 está en 1,20 m.",
    )
    assert not is_reusable_knowledge_reply(ask_scope_prompt())
    assert not is_reusable_knowledge_reply(
        "Se encontró la skill 'red'. ¿Autorizás a Gemini a auditarla?"
    )
    assert not is_reusable_knowledge_reply(
        "No hay ninguna acción o petición específica en tu mensaje, "
        "así que solo te devuelvo el saludo. Estoy funcionando correctamente."
    )
    assert not should_use_semantic_cache("Hola crack! Como estas?")
    assert is_reusable_knowledge_reply("El caudal del canal 12 es 80 l/s.")


def test_parse_context_scope():
    assert parse_context_scope("personal") == "personal"
    assert parse_context_scope("irrigación") == "irrigacion"
    assert parse_context_scope("es contexto de irrigación") == "irrigacion"
    assert parse_context_scope("privado") == "personal"
    assert parse_context_scope("hola qué tal") is None


def test_extract_note_body():
    body = extract_note_body("Guardá esto como contexto: el turno de riego es martes")
    assert "turno de riego" in body.lower()
    assert "guard" not in body.lower()[:10]


def test_detect_google_calendar_intents():
    assert detect_google_intent("qué tengo en la agenda hoy")["action"] == "calendar_list"
    assert (
        detect_google_intent("agendá un evento reunión de riego mañana a las 10")["action"]
        == "calendar_create"
    )


def test_detect_google_gmail_intents():
    assert detect_google_intent("revisá el inbox de gmail")["action"] == "gmail_list"
    assert detect_google_intent("enviá un mail a jefe@example.com")["action"] == "gmail_send"


def test_detect_google_drive_intents():
    assert detect_google_intent("buscá en drive el informe de caudales")["action"] == "drive_search"
    assert detect_google_intent("indexá este archivo de drive al contexto")["action"] == "drive_index"


def test_programar_envio_de_mail_no_es_calendario():
    decision = heuristic_route("Podes programarme el envío de un mail?")
    assert decision is not None
    assert decision.action == "clarify"
    assert "mail" in (decision.ask or "").lower()
    assert detect_google_intent("Podes programarme el envío de un mail?")["action"] == "clarify"


def test_hoy_suelto_no_es_calendario():
    assert heuristic_route("cómo va todo hoy") is None
    assert detect_google_intent("cómo va todo hoy") is None
    assert resolve_command_intent("qué altura tiene el punto 10009").action == "none"


def test_evento_sin_horario_pregunta_no_inventa():
    decision = heuristic_route("agendá un evento reunión de riego")
    assert decision is not None
    assert decision.action == "clarify"
    assert "cuándo" in (decision.ask or "").lower() or "cuando" in (decision.ask or "").lower()


def test_llm_tools_expuestos():
    from app.services.command_router import save_user_context, use_google

    assert use_google.name == "use_google"
    assert save_user_context.name == "save_user_context"


def test_mail_es_google_nativo_no_skill():
    from app.services.command_router import (
        infer_google_action,
        should_use_native_google,
    )

    msg = "Que onda crack! Podés programar un envío de mail?"
    assert should_use_native_google(msg) is True
    assert infer_google_action(msg) == "gmail_send"


def test_parse_send_at_en_minutos():
    from datetime import datetime, timedelta

    from app.services.google_assistant import parse_send_at

    iso = parse_send_at("programalo para que se envíe en 5 minutos")
    assert iso is not None
    when = datetime.fromisoformat(iso)
    delta = when - datetime.now().astimezone()
    assert timedelta(minutes=4) < delta < timedelta(minutes=6)
    assert parse_send_at("mandalo ahora") is None


def test_extract_order_takes_every_part():
    from app.services.order_parse import extract_order_parts

    text = (
        "Mira es para el mail lautiplopez2@gmail.com, el asunto es prueba "
        "y decile hola estoy testeando! Y programalo para que se envíe en 5 minutos"
    )
    parts = extract_order_parts(text)
    assert parts.wants_mail
    assert parts.to == "lautiplopez2@gmail.com"
    assert parts.subject and "prueba" in parts.subject.lower()
    assert parts.body and "testeando" in parts.body.lower()
    assert parts.when_iso
    recap = parts.recap()
    assert "mail" in recap.lower()
    assert "lautiplopez2@gmail.com" in recap
    assert "5" in recap

    word = extract_order_parts("en 5 minutos armame un word con el informe de caudales")
    assert word.wants_word
    assert word.when_iso
    assert "word" in word.recap().lower()


def test_followup_datos_sigue_la_tarea_abierta():
    """El hilo manda: un 'qué datos?' no puede saltar a otra skill/catálogo."""
    from app.services.skill_marketplace import (
        ask_inputs_for_open_task,
        extract_open_task,
        is_asking_for_needed_data,
        resolve_skill_decision,
    )

    assert is_asking_for_needed_data("Que datos necesitas crack?")

    red_ctx = (
        "Que onda mi crack! Escuchame, podés hacer un análisis de red?\n\n"
        "Que datos necesitas crack?"
    )
    assert "análisis de red" in extract_open_task("", context_text=red_ctx).lower()
    red_ask = ask_inputs_for_open_task(red_ctx)
    assert "red" in red_ask.lower()
    assert "caudal" not in red_ask.lower()
    red_dec = resolve_skill_decision(
        "Que datos necesitas crack?",
        context_text=red_ctx,
    )
    assert red_dec["action"] == "clarify"
    assert "red" in (red_dec.get("reply") or "").lower()
    assert "caudal" not in (red_dec.get("reply") or "").lower()

    backup_ctx = (
        "podés hacerme un backup de la base postgres de irrigación?\n\n"
        "qué datos necesitás?"
    )
    backup_ask = ask_inputs_for_open_task(backup_ctx)
    assert "backup" in backup_ask.lower() or "postgres" in backup_ask.lower()
    assert "caudal" not in backup_ask.lower()
    backup_dec = resolve_skill_decision("qué datos necesitás?", context_text=backup_ctx)
    assert backup_dec["action"] == "clarify"
    assert "backup" in (backup_dec.get("reply") or "").lower() or "postgres" in (
        backup_dec.get("reply") or ""
    ).lower()
    assert "lámina" not in (backup_dec.get("reply") or "").lower()

    from app.services.skill_marketplace import (
        clarifying_question_for_unknown,
        is_thread_followup,
    )

    assert is_thread_followup("qué datos necesitás?", backup_ctx)
    dumped = clarifying_question_for_unknown(
        "qué datos necesitás?",
        context_text=backup_ctx,
    )
    assert "postgres" in dumped.lower() or "backup" in dumped.lower()
    assert "caudal" not in dumped.lower()
    assert "lámina" not in dumped.lower()


def test_orden_generica_wol_con_horario():
    from app.services.order_parse import extract_order_parts, looks_like_do_task
    from app.services.skill_marketplace import should_try_skill_marketplace

    msg = "man en 5 minutos necesito que prendas mi PC"
    assert looks_like_do_task(msg)
    assert should_try_skill_marketplace(msg)
    parts = extract_order_parts(msg)
    assert parts.when_iso
    ack = parts.commit_ack()
    assert "5" in ack
    assert "pc" in ack.lower() or "prend" in ack.lower()
