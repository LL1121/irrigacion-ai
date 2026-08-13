"""OAuth Google + cliente de APIs (Calendar, Gmail, Drive)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlencode

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.auth_session import load_google_tokens, save_google_tokens

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.readonly",
]


def google_oauth_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def build_google_auth_url(*, state: str) -> str:
    settings = get_settings()
    if not google_oauth_configured():
        raise RuntimeError("Google OAuth no está configurado (CLIENT_ID/SECRET)")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


def fetch_google_userinfo(access_token: str) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def _credentials_for_user(db: Session, user_id: str) -> Credentials:
    settings = get_settings()
    stored = load_google_tokens(db, user_id)
    if not stored or not stored.get("access_token"):
        raise RuntimeError("No hay tokens de Google para este usuario. Iniciá sesión.")

    creds = Credentials(
        token=stored["access_token"],
        refresh_token=stored.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=GOOGLE_SCOPES,
    )
    if stored.get("expiry") and isinstance(stored["expiry"], datetime):
        expiry = stored["expiry"]
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        creds.expiry = expiry.replace(tzinfo=None)

    if not creds.valid and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        save_google_tokens(
            db,
            user_id=user_id,
            access_token=creds.token or "",
            refresh_token=creds.refresh_token,
            expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
            scopes=" ".join(GOOGLE_SCOPES),
        )
    return creds


def calendar_list_events(
    db: Session,
    user_id: str,
    *,
    days: int = 7,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    creds = _credentials_for_user(db, user_id)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=max(1, days))
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = []
    for ev in result.get("items") or []:
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
        end_at = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
        items.append(
            {
                "id": ev.get("id"),
                "summary": ev.get("summary") or "(sin título)",
                "start": start,
                "end": end_at,
                "location": ev.get("location"),
                "htmlLink": ev.get("htmlLink"),
            }
        )
    return items


def calendar_create_event(
    db: Session,
    user_id: str,
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    creds = _credentials_for_user(db, user_id)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    # Si vienen fechas date-only
    if "T" not in start_iso:
        body["start"] = {"date": start_iso[:10]}
        body["end"] = {"date": end_iso[:10]}
    created = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "id": created.get("id"),
        "summary": created.get("summary"),
        "htmlLink": created.get("htmlLink"),
        "start": created.get("start"),
        "end": created.get("end"),
    }


def gmail_list_messages(
    db: Session,
    user_id: str,
    *,
    query: str = "in:inbox",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    creds = _credentials_for_user(db, user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    listed = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    out: list[dict[str, Any]] = []
    for item in listed.get("messages") or []:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {
            h["name"]: h["value"]
            for h in (msg.get("payload") or {}).get("headers") or []
        }
        out.append(
            {
                "id": msg.get("id"),
                "snippet": msg.get("snippet"),
                "from": headers.get("From"),
                "subject": headers.get("Subject"),
                "date": headers.get("Date"),
            }
        )
    return out


def gmail_send_message(
    db: Session,
    user_id: str,
    *,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    creds = _credentials_for_user(db, user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    mime = MIMEText(body, _charset="utf-8")
    mime["to"] = to
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )
    return {"id": sent.get("id"), "to": to, "subject": subject}


def drive_search_files(
    db: Session,
    user_id: str,
    *,
    query: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    creds = _credentials_for_user(db, user_id)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    safe = (query or "").replace("'", "\\'")
    q = f"fullText contains '{safe}' and trashed=false" if safe else "trashed=false"
    result = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "mimeType": f.get("mimeType"),
            "modifiedTime": f.get("modifiedTime"),
            "webViewLink": f.get("webViewLink"),
        }
        for f in (result.get("files") or [])
    ]


def drive_read_text_file(db: Session, user_id: str, file_id: str) -> dict[str, Any]:
    creds = _credentials_for_user(db, user_id)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    meta = service.files().get(fileId=file_id, fields="id,name,mimeType,webViewLink").execute()
    mime = meta.get("mimeType") or ""
    text_content = ""
    if mime.startswith("application/vnd.google-apps.document"):
        data = service.files().export(fileId=file_id, mimeType="text/plain").execute()
        text_content = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    elif mime.startswith("text/") or mime in {
        "application/json",
        "application/xml",
    }:
        data = service.files().get_media(fileId=file_id).execute()
        text_content = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
    else:
        text_content = (
            f"(Tipo {mime} no se puede leer como texto plano. "
            f"Abrilo en Drive: {meta.get('webViewLink')})"
        )
    return {
        "id": meta.get("id"),
        "name": meta.get("name"),
        "mimeType": mime,
        "webViewLink": meta.get("webViewLink"),
        "text": text_content[:20000],
    }
