"""Memoria de hilo: resumen estructurado + no resetear al catálogo."""

from unittest.mock import patch

from app.services.llm_roles import (
    format_summary_text,
    normalize_thread_summary,
    summarize_thread,
)
from app.services.skill_marketplace import (
    extract_open_task,
    is_asking_for_needed_data,
    resolve_skill_decision,
)
from app.services.thread_memory import (
    RECENT_TURNS_WITH_SUMMARY,
    open_task_from_state,
    recent_history_for_llm,
)


def _backup_state() -> dict:
    summary = normalize_thread_summary(
        {
            "open_task": "backup de la base postgres de irrigación",
            "status": "waiting_inputs",
            "missing": ["destino", "horario"],
            "known": {},
            "facts": ["El usuario pidió un backup de Postgres"],
            "not_this": "catálogo de riego (caudal, lámina)",
        }
    )
    return {
        **summary,
        "summary_json": summary,
        "summary_text": format_summary_text(summary),
    }


def test_normalize_y_texto_del_resumen():
    previous = {"open_task": "vieja", "status": "in_progress", "facts": ["dato"]}
    data = normalize_thread_summary(
        {"open_task": "", "status": "no-existe", "facts": "malo"},
        previous=previous,
    )
    assert data["open_task"] == "vieja"
    assert data["status"] == "in_progress"
    assert data["facts"] == ["dato"]
    text = format_summary_text(
        {
            "open_task": "backup de la base postgres",
            "status": "waiting_inputs",
            "not_this": "catálogo de riego",
        }
    )
    assert "postgres" in text.lower()
    assert "waiting_inputs" in text
    assert "catálogo de riego" in text.lower()


def test_summarize_sin_gemini_no_rompe():
    with patch("app.services.llm_roles.gemini_configured", return_value=False):
        assert summarize_thread("user: hola\nassistant: qué tal") is None


def test_historial_corto_si_hay_resumen():
    history = [{"role": "user", "message": str(i)} for i in range(20)]
    trimmed = recent_history_for_llm(
        history, {"open_task": "x", "summary_text": "ESTADO DEL HILO"}
    )
    assert len(trimmed) == RECENT_TURNS_WITH_SUMMARY
    assert trimmed[0]["message"] == str(20 - RECENT_TURNS_WITH_SUMMARY)
    full = recent_history_for_llm(history, {})
    assert len(full) == 20


def test_followup_usa_tarea_persistida_no_catalogo():
    state = _backup_state()
    assert is_asking_for_needed_data("qué datos necesitás?")
    assert "postgres" in extract_open_task(
        "qué datos necesitás?", thread_state=state
    ).lower()
    decision = resolve_skill_decision(
        "qué datos necesitás?",
        thread_state=state,
    )
    assert decision["action"] == "clarify"
    reply = (decision.get("reply") or "").lower()
    assert "postgres" in reply or "backup" in reply
    assert "caudal" not in reply
    assert "lámina" not in reply
    assert "lamina" not in reply


def test_pedido_nuevo_pisa_resumen_viejo():
    state = _backup_state()
    task = extract_open_task(
        "podés hacer un análisis de red?",
        thread_state=state,
    )
    assert "red" in task.lower()
    assert "backup" not in task.lower()


def test_context_switch_abandona_tarea_abierta():
    """Un comando nuevo autónomo no sigue pidiendo datos de la tarea vieja."""
    from app.services.skill_marketplace import (
        is_context_switch,
        is_thread_followup,
    )

    state = {
        "open_task": "Atender consulta",
        "summary_json": {"open_task": "Atender consulta", "status": "waiting_inputs"},
        "summary_text": "Tarea abierta: Atender consulta",
    }
    msg = "hacé una prueba de velocidad de internet"
    assert is_context_switch(msg, thread_state=state)
    assert not is_thread_followup(msg, thread_state=state)
    task = extract_open_task(msg, thread_state=state)
    assert "velocidad" in task.lower() or "internet" in task.lower()
    assert "atender consulta" not in task.lower()
    decision = resolve_skill_decision(msg, thread_state=state)
    assert decision["action"] in {"download", "clarify"}
    reply = (decision.get("reply") or "").lower()
    assert "atender consulta" not in reply
    assert "destino, archivo" not in reply
    if decision["action"] == "clarify":
        assert "velocidad" in reply or "internet" in reply or "skill" in reply

    assert not is_context_switch("qué datos necesitás?", thread_state=state)
    assert is_thread_followup("qué datos necesitás?", thread_state=state)


def test_sin_resumen_sigue_heuristico():
    ctx = (
        "podés hacerme un backup de la base postgres de irrigación?\n\n"
        "qué datos necesitás?"
    )
    assert "postgres" in extract_open_task("", context_text=ctx).lower()
    assert not open_task_from_state({})
    assert not open_task_from_state(None)


def test_open_task_ninguna_es_estado_limpio():
    from app.services.llm_roles import normalize_thread_summary, sanitize_open_task
    from app.services.skill_marketplace import (
        ask_inputs_for_open_task,
        should_try_skill_marketplace,
    )

    assert sanitize_open_task("Ninguna") == ""
    assert sanitize_open_task("None") == ""
    assert sanitize_open_task("null") == ""
    assert sanitize_open_task("  ") == ""
    assert sanitize_open_task("backup postgres") == "backup postgres"

    state = {
        "open_task": "Ninguna",
        "summary_json": {"open_task": "Ninguna", "status": "waiting_inputs"},
        "summary_text": "Tarea abierta: Ninguna",
    }
    assert open_task_from_state(state) == ""
    assert extract_open_task("cómo andás?", thread_state=state) == ""
    reply = ask_inputs_for_open_task(
        "cómo andás?", thread_state=state
    ).lower()
    assert "ninguna" not in reply
    assert "seguimos con lo de" not in reply

    cleaned = normalize_thread_summary(
        {"open_task": "Ninguna", "status": "waiting_inputs"},
        previous={"open_task": "None"},
    )
    assert cleaned["open_task"] == ""

    assert should_try_skill_marketplace(
        "podrías buscar una skill para hacer un test de velocidad?"
    )
    assert should_try_skill_marketplace("buscar una skill para medir la red")
