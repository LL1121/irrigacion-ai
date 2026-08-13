"""Auth de sesión (JWT) + cifrado de tokens OAuth."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db


def _fernet() -> Fernet:
    settings = get_settings()
    raw = (settings.token_encryption_key or settings.app_jwt_secret or "dev-insecure-key").encode()
    digest = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("No se pudo descifrar el token OAuth") from exc


def create_access_token(*, user_id: str, email: str) -> str:
    settings = get_settings()
    secret = settings.app_jwt_secret or settings.token_encryption_key or "dev-insecure-jwt"
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.app_jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.app_jwt_secret or settings.token_encryption_key or "dev-insecure-jwt"
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada") from exc


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("irrigacion_session")


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    token = _extract_bearer(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    row = db.execute(
        text(
            """
            SELECT id::text AS id, email, name, picture, google_sub
            FROM users
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def require_user(
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Tenés que iniciar sesión con Google")
    return user


def upsert_google_user(
    db: Session,
    *,
    google_sub: str,
    email: str,
    name: str | None,
    picture: str | None,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO users (google_sub, email, name, picture)
            VALUES (:google_sub, :email, :name, :picture)
            ON CONFLICT (google_sub) DO UPDATE SET
                email = EXCLUDED.email,
                name = COALESCE(EXCLUDED.name, users.name),
                picture = COALESCE(EXCLUDED.picture, users.picture),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id::text AS id, email, name, picture, google_sub
            """
        ),
        {
            "google_sub": google_sub,
            "email": email,
            "name": name,
            "picture": picture,
        },
    ).mappings().first()
    db.commit()
    return dict(row)


def save_google_tokens(
    db: Session,
    *,
    user_id: str,
    access_token: str,
    refresh_token: str | None,
    expiry: datetime | None,
    scopes: str | None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO oauth_tokens (
                user_id, provider, access_token_enc, refresh_token_enc,
                token_expiry, scopes, updated_at
            )
            VALUES (
                CAST(:user_id AS uuid), 'google', :access_enc, :refresh_enc,
                :expiry, :scopes, CURRENT_TIMESTAMP
            )
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token_enc = EXCLUDED.access_token_enc,
                refresh_token_enc = COALESCE(
                    EXCLUDED.refresh_token_enc, oauth_tokens.refresh_token_enc
                ),
                token_expiry = EXCLUDED.token_expiry,
                scopes = EXCLUDED.scopes,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "user_id": user_id,
            "access_enc": encrypt_secret(access_token),
            "refresh_enc": encrypt_secret(refresh_token) if refresh_token else None,
            "expiry": expiry,
            "scopes": scopes,
        },
    )
    db.commit()


def load_google_tokens(db: Session, user_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT access_token_enc, refresh_token_enc, token_expiry, scopes
            FROM oauth_tokens
            WHERE user_id = CAST(:user_id AS uuid) AND provider = 'google'
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "access_token": decrypt_secret(row["access_token_enc"]),
        "refresh_token": decrypt_secret(row["refresh_token_enc"]),
        "expiry": row["token_expiry"],
        "scopes": row["scopes"],
    }


def is_tool_whitelisted(db: Session, user_id: str, tool_id: str) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1 FROM tool_whitelist
            WHERE user_id = CAST(:user_id AS uuid) AND tool_id = :tool_id
            LIMIT 1
            """
        ),
        {"user_id": user_id, "tool_id": tool_id},
    ).first()
    return row is not None


def add_tool_whitelist(db: Session, user_id: str, tool_id: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO tool_whitelist (user_id, tool_id)
            VALUES (CAST(:user_id AS uuid), :tool_id)
            ON CONFLICT (user_id, tool_id) DO NOTHING
            """
        ),
        {"user_id": user_id, "tool_id": tool_id},
    )
    db.commit()


def parse_user_id(value: str | UUID | None) -> str | None:
    if value is None:
        return None
    return str(value)
