"""Endpoints de autenticación Google OAuth."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.auth_session import (
    create_access_token,
    get_optional_user,
    require_user,
    save_google_tokens,
    upsert_google_user,
)
from app.services.google_workspace import (
    build_google_auth_url,
    exchange_code_for_tokens,
    fetch_google_userinfo,
    google_oauth_configured,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_OAUTH_STATES: dict[str, float] = {}


def _prune_states() -> None:
    now = datetime.now(timezone.utc).timestamp()
    expired = [k for k, exp in _OAUTH_STATES.items() if exp < now]
    for k in expired:
        _OAUTH_STATES.pop(k, None)


@router.get("/google/start")
def google_start() -> dict[str, str]:
    if not google_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth no configurado. Definí GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET y GOOGLE_REDIRECT_URI."
            ),
        )
    _prune_states()
    state = secrets.token_urlsafe(24)
    _OAUTH_STATES[state] = datetime.now(timezone.utc).timestamp() + 600
    return {"authorize_url": build_google_auth_url(state=state)}


@router.get("/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    settings = get_settings()
    frontend = (settings.frontend_public_url or "").rstrip("/") or str(
        request.base_url
    ).rstrip("/")

    if error:
        return RedirectResponse(f"{frontend}/?auth_error={quote(error)}")
    if not code or not state or state not in _OAUTH_STATES:
        return RedirectResponse(f"{frontend}/?auth_error=invalid_state")
    _OAUTH_STATES.pop(state, None)

    try:
        token_payload = exchange_code_for_tokens(code)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise RuntimeError("Google no devolvió access_token")
        info = fetch_google_userinfo(access_token)
        google_sub = info.get("sub")
        email = info.get("email")
        if not google_sub or not email:
            raise RuntimeError("Google userinfo incompleto")
        user = upsert_google_user(
            db,
            google_sub=google_sub,
            email=email,
            name=info.get("name"),
            picture=info.get("picture"),
        )
        expires_in = int(token_payload.get("expires_in") or 3600)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        save_google_tokens(
            db,
            user_id=user["id"],
            access_token=access_token,
            refresh_token=token_payload.get("refresh_token"),
            expiry=expiry,
            scopes=token_payload.get("scope"),
        )
        jwt_token = create_access_token(user_id=user["id"], email=email)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(f"{frontend}/?auth_error={quote(str(exc)[:120])}")

    response = RedirectResponse(
        f"{frontend}/?auth=ok&access_token={quote(jwt_token)}"
    )
    response.set_cookie(
        key="irrigacion_session",
        value=jwt_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.app_jwt_ttl_hours * 3600,
        path="/",
    )
    return response


@router.get("/me")
def auth_me(user: dict[str, Any] | None = Depends(get_optional_user)) -> dict:
    if not user:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name"),
            "picture": user.get("picture"),
        },
        "google_oauth_configured": google_oauth_configured(),
    }


@router.post("/logout")
def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie("irrigacion_session", path="/")
    return response


@router.get("/session-token")
def session_token(user: dict[str, Any] = Depends(require_user)) -> dict:
    """Útil para clientes Tauri que no comparten cookie con el API."""
    token = create_access_token(user_id=user["id"], email=user["email"])
    return {"access_token": token, "token_type": "bearer"}
