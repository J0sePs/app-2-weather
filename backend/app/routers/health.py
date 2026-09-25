"""Sonda de salud del backend.

No depende ni de Open-Meteo ni del Data Lake, para que los orquestadores puedan
comprobar el proceso sin consumir la API externa.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models import EstadoSalud

router = APIRouter(tags=["salud"])


@router.get(
    "/health",
    response_model=EstadoSalud,
    summary="Sonda de salud del proceso",
)
async def health() -> EstadoSalud:
    """Responde `{"status": "ok"}` mientras el proceso atienda peticiones."""
    return EstadoSalud(status="ok")
