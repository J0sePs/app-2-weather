"""Configuración del backend y constantes del sitio.

Todos los valores tienen un valor por omisión funcional, de modo que el servicio arranca
sin definir ninguna variable de entorno. Cada variable se puede sobreescribir con el
prefijo `MP_`; las de tipo lista se pasan como JSON, por ejemplo
`MP_CORS_ORIGINS='["https://machupicchu.example"]'`.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.datalake import RUTA_POR_DEFECTO_DATALAKE

#: Zona horaria del sitio. "Hoy" para Machu Picchu no es "hoy" en UTC.
ZONA_HORARIA_SITIO = "America/Lima"

#: Coordenadas de Machu Picchu, fijadas por el sistema y no por el cliente.
LATITUD_MACHU_PICCHU = -13.1631
LONGITUD_MACHU_PICCHU = -72.5450

#: Niveles de log que acepta el servicio. Se comparan ya en mayúsculas.
NIVELES_LOG = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def hoy_en_lima() -> date:
    """Devuelve la fecha actual en la zona horaria del sitio."""
    return datetime.now(ZoneInfo(ZONA_HORARIA_SITIO)).date()


class Settings(BaseSettings):
    """Configuración del servicio, leída de variables de entorno con prefijo `MP_`."""

    model_config = SettingsConfigDict(
        env_prefix="MP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ruta_datalake: Path = RUTA_POR_DEFECTO_DATALAKE
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_timeout: float = 4.0
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]
    log_level: str = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalizar_nivel_log(cls, valor: str) -> str:
        """Acepta `debug` o `DEBUG` indistintamente y rechaza niveles inventados.

        Se normaliza aquí, y no en el punto de uso, para que la configuración sea
        autodescriptiva y un `MP_LOG_LEVEL=debug` mal escrito falle al arrancar en
        lugar de emitir una advertencia de logging más adelante.
        """
        if not isinstance(valor, str):
            return valor
        normalizado = valor.strip().upper()
        if normalizado not in NIVELES_LOG:
            raise ValueError(
                f"MP_LOG_LEVEL debe ser uno de {', '.join(NIVELES_LOG)}; "
                f"se recibió {valor!r}"
            )
        return normalizado


@lru_cache
def obtener_settings() -> Settings:
    """Devuelve la configuración del proceso, cacheada para no releerla por petición."""
    return Settings()
