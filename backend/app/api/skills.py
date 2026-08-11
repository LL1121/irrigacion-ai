"""Endpoint de registro/prueba de skills con auditoría Gemini + sandbox Docker."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.sandbox import execute_skill_in_sandbox

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillExecuteRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Código fuente Python de la skill")
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos de entrada expuestos a la skill como input_data",
    )


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
