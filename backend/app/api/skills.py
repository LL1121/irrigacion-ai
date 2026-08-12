"""Endpoints de skills: ejecución directa y aprobación HITL."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.agent import resume_agent
from app.services.sandbox import execute_skill_in_sandbox

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillExecuteRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Código fuente Python de la skill")
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos de entrada expuestos a la skill como input_data",
    )


class SkillApproveRequest(BaseModel):
    session_id: UUID
    approved: bool


@router.post("/execute")
async def execute_skill(payload: SkillExecuteRequest) -> dict[str, Any]:
    try:
        result = await execute_skill_in_sandbox(payload.code, payload.input_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando skill: {exc}",
        ) from exc

    return result


@router.post("/approve")
def approve_skill(
    payload: SkillApproveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        outcome = resume_agent(db, payload.session_id, payload.approved)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Error al reanudar el agente: {exc}",
        ) from exc

    return {
        "session_id": str(payload.session_id),
        "reply": outcome.reply,
        "status": outcome.status,
        "skill_name": outcome.skill_name,
        "skill_description": outcome.skill_description,
        "audit": outcome.audit,
        "approved": payload.approved,
    }
