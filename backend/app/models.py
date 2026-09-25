"""Modelos de la respuesta HTTP de la API.

El esquema es parte del contrato: `site`, `target_date`, `weather` y `prediction`, sin
claves adicionales.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

#: Nombre del sitio, fijo por el sistema.
SITIO = "Machu Picchu"

NivelesAfluencia = Literal["Bajo", "Moderado", "Alto"]


class Clima(BaseModel):
    """El clima esperado para la fecha consultada."""

    temperature_max: float = Field(description="Temperatura máxima en grados Celsius")
    precipitation_probability: int = Field(
        ge=0, le=100, description="Probabilidad máxima de precipitación, en porcentaje"
    )
    condition: str = Field(description="Condición atmosférica en español")


class Prediccion(BaseModel):
    """La estimación de afluencia y su lectura relativa al aforo."""

    estimated_visitors: int = Field(description="Visitantes estimados")
    capacity_percentage: float = Field(
        description="Porcentaje del aforo oficial, redondeado a un decimal"
    )
    crowd_level: NivelesAfluencia = Field(description="Nivel de afluencia")


class RespuestaPrediccion(BaseModel):
    """La respuesta completa de `GET /api/prediction`."""

    site: str = Field(description="Sitio consultado")
    target_date: date = Field(description="Fecha consultada, en YYYY-MM-DD")
    weather: Clima
    prediction: Prediccion


class EstadoSalud(BaseModel):
    """La respuesta de `GET /health`."""

    status: str
