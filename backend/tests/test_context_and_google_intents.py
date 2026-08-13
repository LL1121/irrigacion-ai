"""Tests mínimos de intents de contexto tipado y Google tools."""

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
    assert detect_google_intent("agendá un evento reunión de riego")["action"] == "calendar_create"


def test_detect_google_gmail_intents():
    assert detect_google_intent("revisá el inbox de gmail")["action"] == "gmail_list"
    assert detect_google_intent("enviá un mail a jefe@example.com")["action"] == "gmail_send"


def test_detect_google_drive_intents():
    assert detect_google_intent("buscá en drive el informe de caudales")["action"] == "drive_search"
    assert detect_google_intent("indexá este archivo de drive al contexto")["action"] == "drive_index"
