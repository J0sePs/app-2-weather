"""Lógica de predicción de visitantes.

Cruza el pronóstico de un día con el historial del Data Lake y devuelve un número
explicable: el promedio de los visitantes reales de los días del Data Lake que se
parecen al día consultado en fin de semana o feriado y en clima, y si no hay ninguno,
en temporada.

No depende de `httpx` ni de Open-Meteo: recibe un `Pronostico` como valor, de modo que
sus tests no necesiten red.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMA_DESPEJADO,
    CLIMA_LLUVIA,
    CLIMA_LLUVIA_TORRENCIAL,
    CLIMA_NUBLADO,
    CLIMA_TORMENTA,
    DataLake,
    Registro,
    es_fin_de_semana_o_feriado,
    promedio_visitantes,
    temporada_de,
)
from app.weather import Pronostico, PronosticoDiario

NIVEL_BAJO = "Bajo"
NIVEL_MODERADO = "Moderado"
NIVEL_ALTO = "Alto"

#: Umbrales del nivel de afluencia. El extremo superior de `Moderado` está incluido.
UMBRAL_MODERADO = 3000
UMBRAL_ALTO = 4500

#: Bandas de probabilidad de precipitación que traducen el pronóstico diario a una
#: categoría del vocabulario del Data Lake. La compatibilidad entre el clima prognosis y
#: el del CSV se define por esta banda, no por una categoría más fina.
BANDAS_PRECIPITACION: tuple[tuple[int, int, str], ...] = (
    (0, 5, CLIMA_DESPEJADO),
    (5, 20, CLIMA_NUBLADO),
    (20, 60, CLIMA_LLUVIA),
    (60, 85, CLIMA_LLUVIA_TORRENCIAL),
    (85, 101, CLIMA_TORMENTA),
)

#: Códigos de Open-Meteo que son tormenta aunque la probabilidad de precipitación sea
#: baja. Permiten que un día de tormenta no se compare nunca con un día despejado.
CODIGOS_TORMENTA = frozenset({95, 96, 99})

#: Códigos de lluvia intensa que suben a `lluvia_torrencial` con precipitación normal.
CODIGOS_LLUVIA_INTENSA = frozenset({65, 67, 82})


class ErrorPrediccion(RuntimeError):
    """No hay base de cálculo para la fecha solicitada."""


class ProveedorClima(Protocol):
    """La interfaz de clima que consume la predicción."""

    async def obtener_pronostico(self) -> Pronostico: ...


@dataclass(frozen=True, slots=True)
class ResultadoPrediccion:
    """El resultado del cálculo, independiente del transporte HTTP."""

    fecha: date
    pronostico: PronosticoDiario
    estimados: int
    porcentaje_aforo: float
    nivel_afluencia: str
    categoria_clima: str
    temporada: str
    es_fin_de_semana_o_feriado: bool
    registros_similares: int
    criterio: str


def categoria_climatica(pronostico: PronosticoDiario) -> str:
    """Traduce el pronóstico de un día a una categoría del vocabulario del Data Lake."""
    if pronostico.codigo_clima in CODIGOS_TORMENTA:
        return CLIMA_TORMENTA

    probabilidad = pronostico.probabilidad_precipitacion
    categoria = CLIMA_TORMENTA
    for minimo, maximo, nombre in BANDAS_PRECIPITACION:
        if minimo <= probabilidad < maximo:
            categoria = nombre
            break

    if pronostico.codigo_clima in CODIGOS_LLUVIA_INTENSA and categoria in {
        CLIMA_DESPEJADO,
        CLIMA_NUBLADO,
        CLIMA_LLUVIA,
    }:
        return CLIMA_LLUVIA_TORRENCIAL
    return categoria


def nivel_afluencia(estimados: int) -> str:
    """Deriva el nivel de afluencia de la estimación."""
    if estimados < UMBRAL_MODERADO:
        return NIVEL_BAJO
    if estimados <= UMBRAL_ALTO:
        return NIVEL_MODERADO
    return NIVEL_ALTO


def porcentaje_aforo(estimados: int) -> float:
    """Porcentaje del aforo oficial, redondeado a un decimal."""
    return round(estimados / CAPACIDAD_MAXIMA * 100, 1)


def acotar_visitas(valor: float) -> int:
    """Acota una estimación al rango físico del sitio."""
    return int(min(CAPACIDAD_MAXIMA, max(0, round(valor))))


def dias_similares(
    data_lake: DataLake, fecha_objetivo: date, pronostico: PronosticoDiario
) -> tuple[list[Registro], str, str]:
    """Selecciona los días del historial comparables, en dos niveles.

    Devuelve los registros, el criterio usado y la categoría climática. El primer nivel
    que encuentre coincidencias gana: primero el clima y, si no hay ninguna, la
    temporada, de modo que siempre exista una base de cálculo.
    """
    es_finde = es_fin_de_semana_o_feriado(fecha_objetivo)
    temporada = temporada_de(fecha_objetivo)
    categoria = categoria_climatica(pronostico)

    estrictos = data_lake.filtrar(climas={categoria}, fin_de_semana_o_feriado=es_finde)
    if estrictos:
        return estrictos, "clima", categoria

    relajados = data_lake.filtrar(
        temporadas={temporada}, fin_de_semana_o_feriado=es_finde
    )
    return relajados, "temporada", categoria


def estimar_visitantes(
    data_lake: DataLake, fecha_objetivo: date, pronostico: PronosticoDiario
) -> ResultadoPrediccion:
    """Calcula la estimación de visitantes para una fecha y su pronóstico."""
    registros, criterio, categoria = dias_similares(data_lake, fecha_objetivo, pronostico)

    promedio = promedio_visitantes(registros)
    if promedio is None:
        raise ErrorPrediccion(
            f"No hay días comparables en el historial para el {fecha_objetivo.isoformat()}."
        )

    estimados = acotar_visitas(promedio)
    return ResultadoPrediccion(
        fecha=fecha_objetivo,
        pronostico=pronostico,
        estimados=estimados,
        porcentaje_aforo=porcentaje_aforo(estimados),
        nivel_afluencia=nivel_afluencia(estimados),
        categoria_clima=categoria,
        temporada=temporada_de(fecha_objetivo),
        es_fin_de_semana_o_feriado=es_fin_de_semana_o_feriado(fecha_objetivo),
        registros_similares=len(registros),
        criterio=criterio,
    )


class Predictor:
    """Servicio de predicción. Recibe el Data Lake y consulta el clima bajo demanda."""

    def __init__(self, data_lake: DataLake) -> None:
        self._data_lake = data_lake

    def estimar(
        self, fecha_objetivo: date, pronostico: Pronostico
    ) -> ResultadoPrediccion:
        """Estima la afluencia a partir de un pronóstico ya obtenido.

        El transporte usa esta vía porque necesita la misma respuesta para validar la
        ventana de la fecha, y no debe pedirle el pronóstico dos veces al proveedor.
        """
        return estimar_visitantes(
            self._data_lake, fecha_objetivo, pronostico.para(fecha_objetivo)
        )

    async def predecir(
        self, fecha_objetivo: date, clima: ProveedorClima
    ) -> ResultadoPrediccion:
        """Consulta el pronóstico y estima la afluencia de la fecha objetivo."""
        return self.estimar(fecha_objetivo, await clima.obtener_pronostico())
