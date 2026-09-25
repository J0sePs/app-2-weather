"""Cliente del pronóstico meteorológico de Open-Meteo.

Es la única puerta de salida a Internet del backend. Detrás de esta módulo hay una
interfaz estrecha (`Pronostico`) para que la lógica de predicción se pueda probar sin
red y sin `respx`.

La ventana de pronóstico no es una constante: se deriva de las fechas que el proveedor
devuelve realmente en `daily.time`, tal y como decide `design.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.settings import (
    LATITUD_MACHU_PICCHU,
    LONGITUD_MACHU_PICCHU,
    ZONA_HORARIA_SITIO,
)

#: Variables diarias pedidas a Open-Meteo, en el orden en que se declaran.
VARIABLES_DIARIAS = (
    "temperature_2m_max",
    "precipitation_probability_max",
    "weathercode",
)

#: Traducción explícita de los códigos de condición atmosférica de Open-Meteo.
#: Es un dato declarado en el código y no una tabla descargada en el arranque, para que
#: el mapeo sea auditable y el arranque no dependa de la red.
DESCRIPCIONES_WEATHERCODE: Mapping[int, str] = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna ligera",
    53: "Llovizna moderada",
    55: "Llovizna densa",
    56: "Llovizna helada ligera",
    57: "Llovizna helada intensa",
    61: "Lluvia ligera",
    63: "Lluvia moderada",
    65: "Lluvia intensa",
    66: "Lluvia helada ligera",
    67: "Lluvia helada intensa",
    71: "Nieve ligera",
    73: "Nieve moderada",
    75: "Nieve intensa",
    77: "Granos de nieve",
    80: "Chubascos ligeros",
    81: "Chubascos moderados",
    82: "Chubascos violentos",
    85: "Chubascos de nieve ligeros",
    86: "Chubascos de nieve intensos",
    95: "Tormenta",
    96: "Tormenta con granizo ligero",
    99: "Tormenta con granizo intenso",
}

#: Descripción usada para un código que no esté en la tabla. Un código nuevo de
#: Open-Meteo no debe tumbar la aplicación.
DESCRIPCION_GENERICA = "Condición meteorológica indeterminada"


class WeatherUnavailableError(RuntimeError):
    """No se pudo obtener el pronóstico de Open-Meteo."""


def describir_clima(codigo: Any) -> str:
    """Traduce a español un `weathercode` de Open-Meteo.

    Un código desconocido devuelve una descripción genérica en lugar de fallar.
    """
    if isinstance(codigo, bool):
        return DESCRIPCION_GENERICA
    if isinstance(codigo, int):
        return DESCRIPCIONES_WEATHERCODE.get(codigo, DESCRIPCION_GENERICA)
    if isinstance(codigo, float) and codigo.is_integer():
        return DESCRIPCIONES_WEATHERCODE.get(int(codigo), DESCRIPCION_GENERICA)
    return DESCRIPCION_GENERICA


@dataclass(frozen=True, slots=True)
class PronosticoDiario:
    """El pronóstico de un día concreto."""

    fecha: date
    temperatura_max: float
    probabilidad_precipitacion: int
    codigo_clima: int

    @property
    def condicion(self) -> str:
        """Descripción en español de la condición atmosférica."""
        return describir_clima(self.codigo_clima)


@dataclass(frozen=True, slots=True)
class Pronostico:
    """La ventana de pronóstico que el proveedor ha devuelto realmente.

    `fechas` es la lista real de `daily.time`: la validación de la fecha objetivo se
    hace contra ella, en lugar de contra una constante que puede quedar desfasada.
    """

    por_fecha: Mapping[date, PronosticoDiario]

    @property
    def fechas(self) -> tuple[date, ...]:
        return tuple(sorted(self.por_fecha))

    @property
    def primera_fecha(self) -> date:
        return self.fechas[0]

    @property
    def ultima_fecha(self) -> date:
        return self.fechas[-1]

    def contiene(self, fecha: date) -> bool:
        return fecha in self.por_fecha

    def para(self, fecha: date) -> PronosticoDiario:
        """Devuelve el pronóstico del día, o lanza error si la fecha no está."""
        try:
            return self.por_fecha[fecha]
        except KeyError as exc:
            raise KeyError(fecha) from exc


def _construir_pronostico(payload: Any) -> Pronostico:
    """Convierte el payload de Open-Meteo en un `Pronostico`, validando su forma."""
    if not isinstance(payload, Mapping):
        raise WeatherUnavailableError(
            "Open-Meteo devolvió una respuesta que no es un objeto JSON."
        )

    diario = payload.get("daily")
    if not isinstance(diario, Mapping):
        raise WeatherUnavailableError(
            "Open-Meteo devolvió una respuesta sin la clave 'daily'."
        )

    series: dict[str, list[Any]] = {}
    for variable in VARIABLES_DIARIAS:
        valores = diario.get(variable)
        if not isinstance(valores, list) or not valores:
            raise WeatherUnavailableError(
                f"Open-Meteo devolvió la serie diaria {variable!r} vacía o ausente."
            )
        series[variable] = valores

    fechas_texto = diario.get("time")
    if not isinstance(fechas_texto, list) or not fechas_texto:
        raise WeatherUnavailableError(
            "Open-Meteo devolvió la serie diaria 'time' vacía o ausente."
        )

    longitudes = {len(valores) for valores in series.values()} | {len(fechas_texto)}
    if len(longitudes) != 1:
        raise WeatherUnavailableError(
            f"Open-Meteo devolvió series diarias de longitudes distintas: {sorted(longitudes)}."
        )

    por_fecha: dict[date, PronosticoDiario] = {}
    for indice, fecha_texto in enumerate(fechas_texto):
        try:
            fecha = date.fromisoformat(str(fecha_texto))
            temperatura = float(series["temperature_2m_max"][indice])
            probabilidad = int(series["precipitation_probability_max"][indice])
            codigo = series["weathercode"][indice]
        except (TypeError, ValueError) as exc:
            raise WeatherUnavailableError(
                f"Open-Meteo devolvió un valor diario ilegible en la posición {indice}: {exc}"
            ) from exc

        por_fecha[fecha] = PronosticoDiario(
            fecha=fecha,
            temperatura_max=temperatura,
            probabilidad_precipitacion=min(100, max(0, probabilidad)),
            codigo_clima=codigo if isinstance(codigo, int) else 0,
        )

    return Pronostico(por_fecha=por_fecha)


class ClienteOpenMeteo:
    """Consulta el pronóstico diario de Machu Picchu en Open-Meteo.

    Se le puede inyectar un `httpx.AsyncClient` compartido (lo hace el `lifespan` de la
    aplicación); si no se le inyecta ninguno, abre y cierra uno por petición.
    """

    def __init__(
        self,
        url_base: str = "https://api.open-meteo.com/v1/forecast",
        timeout: float = 4.0,
        cliente: httpx.AsyncClient | None = None,
    ) -> None:
        self._url_base = url_base
        self._timeout = timeout
        self._cliente = cliente

    def _parametros(self) -> dict[str, str]:
        """Parámetros de la consulta. Las coordenadas son fijas y no las aporta el cliente."""
        return {
            "latitude": str(LATITUD_MACHU_PICCHU),
            "longitude": str(LONGITUD_MACHU_PICCHU),
            "daily": ",".join(VARIABLES_DIARIAS),
            "timezone": ZONA_HORARIA_SITIO,
        }

    async def obtener_pronostico(self) -> Pronostico:
        """Devuelve la ventana de pronóstico disponible, o lanza `WeatherUnavailableError`.

        Cualquier fallo de red, de estado o de forma del payload se traduce a la misma
        excepción de dominio, para que la API responda 502 en vez de propagar un error
        de `httpx` como un 500 opaco.
        """
        parametros = self._parametros()

        if self._cliente is not None:
            return await self._consultar(self._cliente, parametros)

        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            return await self._consultar(cliente, parametros)

    async def _consultar(
        self, cliente: httpx.AsyncClient, parametros: dict[str, str]
    ) -> Pronostico:
        try:
            respuesta = await cliente.get(self._url_base, params=parametros)
            respuesta.raise_for_status()
        except httpx.TimeoutException as exc:
            raise WeatherUnavailableError(
                "Open-Meteo no respondió dentro del tiempo de espera configurado."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise WeatherUnavailableError(
                f"Open-Meteo respondió con estado {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise WeatherUnavailableError(
                f"No se pudo consultar Open-Meteo: {exc}"
            ) from exc

        try:
            payload = respuesta.json()
        except ValueError as exc:
            raise WeatherUnavailableError(
                "Open-Meteo devolvió un cuerpo que no es JSON válido."
            ) from exc

        return _construir_pronostico(payload)
