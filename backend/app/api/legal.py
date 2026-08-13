"""Redirecciones legales: la política vive en el dominio institucional."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["legal"])

PRIVACY_URL = "https://irrigacionmalargue.net/politicas-privacidad"


def _to_privacy() -> RedirectResponse:
    return RedirectResponse(url=PRIVACY_URL, status_code=302)


@router.get("/politicas-privacidad")
def privacy_policy_es() -> RedirectResponse:
    return _to_privacy()


@router.get("/api/legal/privacidad")
def privacy_policy_api_alias() -> RedirectResponse:
    return _to_privacy()


@router.get("/privacy-policy")
def privacy_policy_en_alias() -> RedirectResponse:
    return _to_privacy()


@router.get("/privacy")
def privacy_short_alias() -> RedirectResponse:
    return _to_privacy()
