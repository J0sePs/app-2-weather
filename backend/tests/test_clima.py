"""Cliente de Open-Meteo: mapeo de `weathercode`, URL de consulta y casos de fallo.

Se usa `respx` para interceptar `httpx`, de modo que la suite no sale a la red.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.weather import (
    DESCRIPCION_GENERICA,
    VARIABLES_DIARIAS,
    ClienteOpenMeteo,
    Pronostico,
    WeatherUnavailableError,
    _construir_pronostico,
    describir_clima,
)

URL_BASE = "https://api.open-meteo.com/v1/forecast"


def payload_de_ejemplo(
    fechas: list[str] | None = None,
    *,
    temperatura: list[float] | None = None,
    probabilidad: list[int] | None = None,
    weathercode: list[int] | None = None,
) -> dict:
    """Payload con la forma real de la respuesta diaria de Open-Meteo."""
    fechas = fechas or ["2026-09-25", "2026-09-26", "2026-09-27"]
    n = len(fechas)
    return {
        "latitude": -13.1631,
        "longitude": -72.545,
        "timezone": "America/Lima",
        "daily": {
            "time": fechas,
            "temperature_2m_max": temperatura or [24.5] * n,
            "precipitation_probability_max": probabilidad or [15] * n,
            "weathercode": weathercode or [3] * n,
        },
    }


class TestDescripcionDelClima:
    @pytest.mark.parametrize(
        ("codigo", "esperado"),
        [
            (0, "Despejado"),
            (1, "Mayormente despejado"),
            (2, "Parcialmente nublado"),
            (3, "Nublado"),
            (45, "Niebla"),
            (61, "Lluvia ligera"),
            (63, "Lluvia moderada"),
            (65, "Lluvia intensa"),
            (80, "Chubascos ligeros"),
            (82, "Chubascos violentos"),
            (95, "Tormenta"),
            (99, "Tormenta con granizo intenso"),
        ],
    )
    def test_los_codigos_representativos_se_traducen(self, codigo: int, esperado: str) -> None:
        assert describir_clima(codigo) == esperado

    def test_un_codigo_inventado_no_lanza_excepcion(self) -> None:
        assert describir_clima(4242) == DESCRIPCION_GENERICA

    @pytest.mark.parametrize("codigo", [None, "soleado", 3.5, True, -1, 1000])
    def test_entradas_no_numericas_no_lanzan_excepcion(self, codigo: object) -> None:
        assert describir_clima(codigo) == DESCRIPCION_GENERICA

    def test_un_float_entero_se_traduce_como_entero(self) -> None:
        assert describir_clima(3.0) == "Nublado"

    def test_la_descripcion_nunca_es_el_codigo_crudo(self) -> None:
        for codigo in (0, 3, 61, 95):
            assert describir_clima(codigo) != str(codigo)


class TestConsultaDelPronostico:
    async def test_consulta_las_coordenadas_fijas_de_machu_picchu(self) -> None:
        with respx.mock:
            ruta = respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            await ClienteOpenMeteo().obtener_pronostico()

        peticion = ruta.calls[0].request
        url = peticion.url
        assert url.params["latitude"] == "-13.1631"
        assert url.params["longitude"] == "-72.545"
        assert url.params["timezone"] == "America/Lima"
        assert url.params["daily"] == ",".join(VARIABLES_DIARIAS)
        for variable in VARIABLES_DIARIAS:
            assert variable in url.params["daily"]

    async def test_hace_una_sola_peticion_por_consulta(self) -> None:
        with respx.mock:
            ruta = respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            await ClienteOpenMeteo().obtener_pronostico()
        assert ruta.call_count == 1

    async def test_el_cliente_crea_su_propio_cliente_con_el_timeout_configurado(self) -> None:
        with respx.mock:
            ruta = respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            await ClienteOpenMeteo(timeout=1.5).obtener_pronostico()
        assert ruta.call_count == 1

    async def test_el_cliente_inyectado_se_reutiliza(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            async with httpx.AsyncClient() as cliente:
                antes = cliente
                pronostico = await ClienteOpenMeteo(cliente=antes).obtener_pronostico()
        assert pronostico.ultima_fecha == date(2026, 9, 27)

    async def test_devuelve_las_fechas_realmente_disponibles(self) -> None:
        fechas = ["2026-09-25", "2026-09-26"]
        with respx.mock:
            respx.get(URL_BASE).mock(
                return_value=httpx.Response(
                    200, json=payload_de_ejemplo(fechas, weathercode=[0, 95])
                )
            )
            pronostico = await ClienteOpenMeteo().obtener_pronostico()

        assert pronostico.fechas == (date(2026, 9, 25), date(2026, 9, 26))
        assert pronostico.primera_fecha == date(2026, 9, 25)
        assert pronostico.ultima_fecha == date(2026, 9, 26)
        assert pronostico.contiene(date(2026, 9, 26)) is True
        assert pronostico.contiene(date(2026, 10, 10)) is False

    async def test_una_ventana_corta_se_refleja_en_la_ultima_fecha(self) -> None:
        """La ventana se deriva de la respuesta, no de una constante del código."""
        fechas = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"]
        with respx.mock:
            respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo(fechas))
            )
            pronostico = await ClienteOpenMeteo().obtener_pronostico()
        assert pronostico.ultima_fecha == date(2026, 9, 28)

    async def test_los_valores_del_dia_son_legibles(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(
                return_value=httpx.Response(
                    200,
                    json=payload_de_ejemplo(
                        ["2026-09-25", "2026-09-26"],
                        temperatura=[24.5, 12.0],
                        probabilidad=[15, 95],
                        weathercode=[3, 95],
                    ),
                )
            )
            pronostico = await ClienteOpenMeteo().obtener_pronostico()

        benigno = pronostico.para(date(2026, 9, 25))
        assert benigno.temperatura_max == 24.5
        assert benigno.probabilidad_precipitacion == 15
        assert benigno.condicion == "Nublado"

        tormentoso = pronostico.para(date(2026, 9, 26))
        assert tormentoso.condicion == "Tormenta"
        assert tormentoso.probabilidad_precipitacion == 95

    async def test_para_una_fecha_fuera_de_la_ventana_lanza_error(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            pronostico = await ClienteOpenMeteo().obtener_pronostico()
        with pytest.raises(KeyError):
            pronostico.para(date(2026, 10, 5))


class TestCasosDeFallo:
    async def test_un_timeout_produce_weather_unavailable(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(side_effect=httpx.ReadTimeout("se agotó el tiempo"))
            with pytest.raises(WeatherUnavailableError) as error:
                await ClienteOpenMeteo().obtener_pronostico()
        assert "tiempo de espera" in str(error.value)

    @pytest.mark.parametrize("estado", [400, 404, 429, 500, 503])
    async def test_un_error_de_estado_produce_weather_unavailable(self, estado: int) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(return_value=httpx.Response(estado, json={}))
            with pytest.raises(WeatherUnavailableError) as error:
                await ClienteOpenMeteo().obtener_pronostico()
        assert str(estado) in str(error.value)

    async def test_un_error_de_conexion_produce_weather_unavailable(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(side_effect=httpx.ConnectError("sin ruta"))
            with pytest.raises(WeatherUnavailableError):
                await ClienteOpenMeteo().obtener_pronostico()

    async def test_un_cuerpo_no_json_produce_weather_unavailable(self) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(return_value=httpx.Response(200, text="<html>"))
            with pytest.raises(WeatherUnavailableError, match="no es JSON"):
                await ClienteOpenMeteo().obtener_pronostico()

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"daily": {}},
            {"daily": {"time": []}},
            {"otra_cosa": 1},
            {
                "daily": {
                    "time": ["2026-09-25"],
                    "temperature_2m_max": [24.5],
                    "weathercode": [3],
                }
            },
            {
                "daily": {
                    "time": ["2026-09-25", "2026-09-26"],
                    "temperature_2m_max": [24.5],
                    "precipitation_probability_max": [10, 20],
                    "weathercode": [3, 3],
                }
            },
            {
                "daily": {
                    "time": ["no-es-fecha"],
                    "temperature_2m_max": [24.5],
                    "precipitation_probability_max": [10],
                    "weathercode": [3],
                }
            },
            {
                "daily": {
                    "time": ["2026-09-25"],
                    "temperature_2m_max": ["caliente"],
                    "precipitation_probability_max": [10],
                    "weathercode": [3],
                }
            },
        ],
    )
    async def test_un_payload_sin_las_claves_esperadas_produce_weather_unavailable(
        self, payload: dict
    ) -> None:
        with respx.mock:
            respx.get(URL_BASE).mock(return_value=httpx.Response(200, json=payload))
            with pytest.raises(WeatherUnavailableError):
                await ClienteOpenMeteo().obtener_pronostico()

    async def test_ningun_fallo_propagaba_la_excepcion_de_httpx(self) -> None:
        """El contrato es `WeatherUnavailableError`, nunca `httpx.HTTPError`."""
        fallos: list[httpx.HTTPError] = [
            httpx.ReadTimeout("t"),
            httpx.ConnectTimeout("t"),
            httpx.ConnectError("c"),
            httpx.RemoteProtocolError("r"),
        ]
        for fallo in fallos:
            with respx.mock:
                respx.get(URL_BASE).mock(side_effect=fallo)
                with pytest.raises(WeatherUnavailableError):
                    await ClienteOpenMeteo().obtener_pronostico()

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            "no soy un objeto",
            42,
            None,
        ],
        ids=["lista", "cadena", "numero", "nulo"],
    )
    def test_un_payload_que_no_es_objeto_produce_weather_unavailable(
        self, payload: object
    ) -> None:
        with pytest.raises(WeatherUnavailableError, match="objeto JSON"):
            _construir_pronostico(payload)

    @pytest.mark.parametrize(
        ("diario", "esperado"),
        [
            (
                {
                    "temperature_2m_max": [20.0],
                    "precipitation_probability_max": [5],
                    "weathercode": [0],
                },
                "time",
            ),
            (
                {
                    "time": [],
                    "temperature_2m_max": [],
                    "precipitation_probability_max": [],
                    "weathercode": [],
                },
                "temperature_2m_max",
            ),
            (
                {
                    "time": "2026-09-25",
                    "temperature_2m_max": [20.0],
                    "precipitation_probability_max": [5],
                    "weathercode": [0],
                },
                "time",
            ),
        ],
        ids=["sin-time", "series-vacias", "time-no-es-lista"],
    )
    def test_la_serie_de_fechas_inutilizable_produce_weather_unavailable(
        self, diario: dict, esperado: str
    ) -> None:
        """Sin una serie diaria utilizable no se puede fijar la ventana de pronóstico."""
        with pytest.raises(WeatherUnavailableError, match=esperado):
            _construir_pronostico({"daily": diario})


class TestNormalizacion:
    def test_la_probabilidad_se_acota_a_0_100(self) -> None:
        pronostico = _construir_pronostico(
            payload_de_ejemplo(
                ["2026-09-25", "2026-09-26"], probabilidad=[-10, 180]
            )
        )
        assert pronostico.para(date(2026, 9, 25)).probabilidad_precipitacion == 0
        assert pronostico.para(date(2026, 9, 26)).probabilidad_precipitacion == 100

    def test_el_rango_de_fechas_esta_ordenado(self) -> None:
        pronostico = _construir_pronostico(
            payload_de_ejemplo(
                ["2026-09-27", "2026-09-25", "2026-09-26"],
                temperatura=[1.0, 2.0, 3.0],
                probabilidad=[1, 2, 3],
                weathercode=[0, 1, 2],
            )
        )
        assert pronostico.fechas == (
            date(2026, 9, 25),
            date(2026, 9, 26),
            date(2026, 9, 27),
        )
        assert pronostico.primera_fecha == date(2026, 9, 25)
        assert pronostico.ultima_fecha == date(2026, 9, 27)

    def test_una_ventana_de_un_solo_dia_es_valida(self) -> None:
        pronostico = _construir_pronostico(payload_de_ejemplo(["2026-09-25"]))
        assert pronostico.fechas == (date(2026, 9, 25),)
        assert pronostico.primera_fecha == pronostico.ultima_fecha

    def test_el_pronostico_esta_congelado(self) -> None:
        pronostico = _construir_pronostico(payload_de_ejemplo(["2026-09-25"]))
        with pytest.raises(Exception):
            pronostico.por_fecha = {}  # type: ignore[misc]

    def test_un_weathercode_desconocido_no_impide_construir_el_pronostico(self) -> None:
        pronostico = _construir_pronostico(
            payload_de_ejemplo(["2026-09-25"], weathercode=[4242])
        )
        assert pronostico.para(date(2026, 9, 25)).condicion == DESCRIPCION_GENERICA

    def test_la_url_base_es_configurable(self) -> None:
        cliente = ClienteOpenMeteo(url_base="https://otro.example/forecast")
        assert cliente._url_base == "https://otro.example/forecast"

    async def test_se_puede_consultar_una_url_base_alternativa(self) -> None:
        with respx.mock:
            ruta = respx.get("https://otro.example/forecast").mock(
                return_value=httpx.Response(200, json=payload_de_ejemplo())
            )
            await ClienteOpenMeteo(url_base="https://otro.example/forecast").obtener_pronostico()
        assert ruta.call_count == 1

    def test_el_tipo_de_pronostico_expone_la_ventana(self) -> None:
        pronostico: Pronostico = _construir_pronostico(payload_de_ejemplo())
        assert len(pronostico.fechas) == 3
