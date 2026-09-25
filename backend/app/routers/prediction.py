"""Endpoint de predicción de afluencia.

La validación de la fecha ocurre en dos momentos, a propósito: el formato y que no sea
una fecha pasada se rechazan sin salir a la red, y la ventana de pronóstico se valida
contra las fechas que Open-Meteo devolvió realmente.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models import SITIO, Clima, Prediccion, RespuestaPrediccion
from app.prediction import Predictor
from app.settings import hoy_en_lima
from app.weather import ClienteOpenMeteo, Pronostico

router = APIRouter(prefix="/api", tags=["predicción"])

#: Los dos casos de 422 que se pueden decidir sin consultar al proveedor.
FORMATO_ESPERADO = "YYYY-MM-DD"

#: 422 escrito como literal: Starlette renombró su constante y no queremos
#: atarnos a una denominación que cambia entre versiones.
ESTADO_NO_PROCESABLE = 422


def obtener_predictor(request: Request) -> Predictor:
    """Devuelve el predictor con el Data Lake cargado en el ciclo de vida."""
    return Predictor(request.app.state.datalake)


def obtener_clima(request: Request) -> ClienteOpenMeteo:
    """Devuelve el cliente de Open-Meteo compartido del ciclo de vida."""
    return request.app.state.clima


def _parsear_fecha(valor: str) -> date:
    """Interpreta el parámetro `date` o responde 422."""
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise HTTPException(
            status_code=ESTADO_NO_PROCESABLE,
            detail=(
                f"La fecha {valor!r} no tiene un formato válido. "
                f"Se espera el formato {FORMATO_ESPERADO}."
            ),
        ) from exc


def _rechazar_si_es_pasada(fecha: date, hoy: date) -> None:
    """Responde 422 si la fecha ya pasó."""
    if fecha < hoy:
        raise HTTPException(
            status_code=ESTADO_NO_PROCESABLE,
            detail=(
                f"La fecha {fecha.isoformat()} ya pasó. "
                f"Sólo se admiten fechas desde hoy, {hoy.isoformat()}."
            ),
        )


def _rechazar_si_esta_fuera_de_la_ventana(fecha: date, pronostico: Pronostico) -> None:
    """Responde 422 si la fecha no está en la ventana que devolvió el proveedor."""
    if pronostico.contiene(fecha):
        return

    raise HTTPException(
        status_code=ESTADO_NO_PROCESABLE,
        detail=(
            f"La fecha {fecha.isoformat()} está fuera de la ventana de pronóstico. "
            f"La última fecha consultable es {pronostico.ultima_fecha.isoformat()}."
        ),
    )


@router.get(
    "/prediction",
    response_model=RespuestaPrediccion,
    summary="Predicción de afluencia para una fecha",
)
async def prediccion(
    fecha: str | None = Query(
        default=None,
        alias="date",
        description="Fecha objetivo en YYYY-MM-DD. Por omisión, hoy en America/Lima.",
    ),
    predictor: Predictor = Depends(obtener_predictor),
    clima: ClienteOpenMeteo = Depends(obtener_clima),
) -> RespuestaPrediccion:
    """Devuelve clima y estimación de visitantes de la fecha objetivo."""
    hoy = hoy_en_lima()

    if fecha is None:
        fecha_objetivo = hoy
    else:
        fecha_objetivo = _parsear_fecha(fecha)
        _rechazar_si_es_pasada(fecha_objetivo, hoy)

    # El error de clima se propaga al manejador registrado, que lo traduce a 502.
    pronostico = await clima.obtener_pronostico()
    _rechazar_si_esta_fuera_de_la_ventana(fecha_objetivo, pronostico)

    resultado = predictor.estimar(fecha_objetivo, pronostico)

    return RespuestaPrediccion(
        site=SITIO,
        target_date=resultado.fecha,
        weather=Clima(
            temperature_max=resultado.pronostico.temperatura_max,
            precipitation_probability=resultado.pronostico.probabilidad_precipitacion,
            condition=resultado.pronostico.condicion,
        ),
        prediction=Prediccion(
            estimated_visitors=resultado.estimados,
            capacity_percentage=resultado.porcentaje_aforo,
            crowd_level=resultado.nivel_afluencia,
        ),
    )
