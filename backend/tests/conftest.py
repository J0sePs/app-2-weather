"""Fixtures compartidas de la suite del backend."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.datalake import (
    COLUMNAS,
    RUTA_POR_DEFECTO_DATALAKE,
    DataLake,
    cargar_data_lake,
)
from app.main import crear_app
from app.settings import Settings

CSV_EN_LINEA_ENCABEZADO_OK = ",".join(COLUMNAS)


@pytest.fixture(scope="session")
def ruta_csv_canonico() -> Path:
    """Ruta del CSV canónico versionado en el repositorio."""
    return RUTA_POR_DEFECTO_DATALAKE


@pytest.fixture(scope="session")
def data_lake_canonico(ruta_csv_canonico: Path) -> DataLake:
    """El Data Lake canónico, cargado una vez por sesión."""
    return cargar_data_lake(ruta_csv_canonico)


@pytest.fixture(scope="session")
def registros(data_lake_canonico: DataLake) -> list:
    return list(data_lake_canonico)


@pytest.fixture
def escribir_csv(tmp_path: Path) -> Callable[[str, str], Path]:
    """Devuelve una función que escribe un CSV de prueba y devuelve su ruta."""

    def _escribir(nombre: str, contenido: str) -> Path:
        ruta = tmp_path / nombre
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    return _escribir


@pytest.fixture
def hoy() -> date:
    """Fecha actual en la zona horaria del sitio."""
    from app.settings import hoy_en_lima

    return hoy_en_lima()


def construir_app(
    ruta_datalake: Path | str | None = None,
    **ajustes: object,
) -> FastAPI:
    """Crea una aplicación aislada, con su propia configuración y su propio estado."""
    configuracion = Settings(
        ruta_datalake=Path(ruta_datalake) if ruta_datalake is not None else RUTA_POR_DEFECTO_DATALAKE,
        **ajustes,  # type: ignore[arg-type]
    )
    return crear_app(configuracion)


async def abrir_cliente(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Ejecuta el `lifespan` y abre un cliente ASGI, sin abrir ningún puerto.

    `httpx.ASGITransport` no dispara los eventos del ciclo de vida, así que se entra en
    el contexto del `lifespan` a mano, igual que hace el servidor real.
    """
    async with app.router.lifespan_context(app):  # type: ignore[attr-defined]
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte, base_url="http://testserver"
        ) as cliente:
            yield cliente


@pytest.fixture
async def app_de_prueba(ruta_csv_canonico: Path) -> FastAPI:
    """Aplicación con el Data Lake canónico y la configuración por omisión."""
    return construir_app(ruta_csv_canonico)


@pytest.fixture
async def cliente(app_de_prueba: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP contra la aplicación, sin puertos abiertos."""
    async for cliente in abrir_cliente(app_de_prueba):
        yield cliente


class ClimaSimulado:
    """Doble de la interfaz de clima, sin red. Los tests de predicción lo usan."""

    def __init__(self, por_fecha: dict[date, object]) -> None:
        self._por_fecha = por_fecha
        self.llamadas = 0

    async def obtener_pronostico(self):
        from app.weather import Pronostico

        self.llamadas += 1
        return Pronostico(por_fecha=self._por_fecha)


class ClimaQueRevienta:
    """Proveedor de clima que falla siempre, para probar el camino de error."""

    def __init__(self, excepcion: Exception) -> None:
        self.excepcion = excepcion

    async def obtener_pronostico(self):
        raise self.excepcion
