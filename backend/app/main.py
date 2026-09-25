"""Fábrica de la aplicación FastAPI y su ciclo de vida.

El Data Lake se carga una sola vez en el `lifespan` y se guarda en `app.state`, de modo
que el fallo por archivo ausente o malformado ocurre en el arranque, que es donde el
mensaje que sugiere ejecutar el generador resulta útil. `app.state` evita un singleton a
nivel de módulo, lo que permite que dos aplicaciones del mismo proceso usen Data Lakes
distintos en los tests.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.datalake import cargar_data_lake
from app.routers import health, prediction
from app.settings import Settings, obtener_settings
from app.weather import ClienteOpenMeteo, WeatherUnavailableError

#: Título y versión que aparecen en la documentación interactiva.
TITULO = "Predicción de Afluencia - Machu Picchu"
VERSION = "0.1.0"

#: Mensaje que ve el usuario cuando el proveedor de clima no está disponible. Lo escribe
#: una persona, no se infiere de un traceback, y no filtra detalle técnico.
MENSAJE_CLIMA_NO_DISPONIBLE = (
    "No se pudo obtener el pronóstico del clima para Machu Picchu. "
    "Vuelve a intentarlo en unos minutos."
)

logger = logging.getLogger("app")


async def manejar_clima_no_disponible(
    request: Request, exc: WeatherUnavailableError
) -> JSONResponse:
    """Traduce un fallo de Open-Meteo a 502, no a un 500 genérico."""
    logger.warning("Open-Meteo no disponible: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"detail": MENSAJE_CLIMA_NO_DISPONIBLE},
    )


def crear_app(configuracion: Settings | None = None) -> FastAPI:
    """Crea una instancia de la aplicación, parametrizada por su configuración.

    Cada instancia tiene su propio `lifespan` y su propio `app.state`, así que dos
    aplicaciones conviven en el mismo proceso con datos distintos.
    """
    ajustes = configuracion if configuracion is not None else obtener_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.datalake = cargar_data_lake(ajustes.ruta_datalake)
        async with httpx.AsyncClient(timeout=ajustes.open_meteo_timeout) as cliente:
            app.state.clima = ClienteOpenMeteo(
                url_base=ajustes.open_meteo_base_url,
                timeout=ajustes.open_meteo_timeout,
                cliente=cliente,
            )
            yield

    logging.getLogger("app").setLevel(ajustes.log_level)

    app = FastAPI(
        title=TITULO,
        version=VERSION,
        summary="Estimación de visitantes a Machu Picchu a partir del clima y el historial.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ajustes.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(prediction.router)
    app.add_exception_handler(WeatherUnavailableError, manejar_clima_no_disponible)

    return app


#: Instancia que sirve uvicorn: `uvicorn app.main:app`.
app = crear_app()
