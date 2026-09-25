"""Pruebas de la API HTTP: ciclo de vida, salud, predicción y contrato.

Ninguna prueba abre un puerto: se entra en el `lifespan` a mano y se habla con la
aplicación a través de `httpx.ASGITransport`. Open-Meteo se intercepta con `respx`, de
modo que la suite es determinista y no consume la API pública.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from pydantic import ValidationError as PydanticValidationError

from app.datalake import COLUMNAS, RUTA_POR_DEFECTO_DATALAKE, cargar_data_lake
from app.models import RespuestaPrediccion
from app.settings import Settings, obtener_settings
from app.weather import WeatherUnavailableError
from tests.conftest import ClimaQueRevienta, construir_app, abrir_cliente

#: Origen permitido por la configuración por omisión.
ORIGEN_PERMITIDO = "http://localhost:4200"
ORIGEN_AHORA_RECHAZADO = "https://sitio-malicioso.example"

def respuesta_clima(desde: date, dias: int = 5) -> httpx.Response:
    """Pronóstico estable y reproducible: despejado, 22 °C, 10 % de lluvia."""
    fechas = [(desde + timedelta(days=i)).isoformat() for i in range(dias)]
    return httpx.Response(
        200,
        json={
            "daily": {
                "time": fechas,
                "temperature_2m_max": [22.0] * dias,
                "precipitation_probability_max": [10] * dias,
                "weathercode": [0] * dias,
            }
        },
    )


def clima_tormenta(desde: date, dias: int = 5) -> httpx.Response:
    fechas = [(desde + timedelta(days=i)).isoformat() for i in range(dias)]
    return httpx.Response(
        200,
        json={
            "daily": {
                "time": fechas,
                "temperature_2m_max": [14.0] * dias,
                "precipitation_probability_max": [95] * dias,
                "weathercode": [95] * dias,
            }
        },
    )


def url_open_meteo() -> str:
    return f"{obtener_settings().open_meteo_base_url}"


class TestCicloDeVida:
    """3.4: el Data Lake se carga en el `lifespan` y vive en `app.state`."""

    async def test_el_datalake_queda_disponible_en_el_estado(
        self, app_de_prueba: FastAPI
    ) -> None:
        async for _ in abrir_cliente(app_de_prueba):
            assert len(app_de_prueba.state.datalake) == 730
            assert app_de_prueba.state.clima is not None

    async def test_dos_aplicaciones_en_el_mismo_proceso_usan_datalakes_distintos(
        self, escribir_csv, ruta_csv_canonico
    ) -> None:
        contenido = ",".join(COLUMNAS) + "\n" + "\n".join(
            [
                "2026-09-05,sábado,seca,despejado,22.0,true,1000",
                "2026-09-06,domingo,seca,despejado,21.0,true,1100",
                "2026-09-07,lunes,seca,despejado,20.0,false,1200",
            ]
        ) + "\n"
        ruta_pequena = escribir_csv("otro.csv", contenido)

        app_a = construir_app(ruta_csv_canonico)
        app_b = construir_app(ruta_pequena)

        async for cliente_a in abrir_cliente(app_a):
            async for cliente_b in abrir_cliente(app_b):
                assert app_a.state.datalake is not app_b.state.datalake
                assert len(app_a.state.datalake) == 730
                assert len(app_b.state.datalake) == 3

                objetivo = date.today().isoformat()
                with respx.mock:
                    respx.get(url_open_meteo()).mock(
                        side_effect=lambda request: respuesta_clima(date.today(), 3)
                    )
                    r_a = await cliente_a.get("/api/prediction")
                    r_b = await cliente_b.get("/api/prediction")
                assert r_a.status_code == 200
                assert r_b.status_code == 200
                # El Data Lake de 3 días promedia 1100, el canónico da miles de visitas.
                assert r_b.json()["prediction"]["estimated_visitors"] < r_a.json()["prediction"]["estimated_visitors"]

    async def test_una_aplicacion_se_puede_arrancar_dos_veces(
        self, app_de_prueba: FastAPI
    ) -> None:
        """El `lifespan` es reentrante: cerrar una instancia no ensucia la otra."""
        for _ in range(2):
            async for cliente in abrir_cliente(app_de_prueba):
                respuesta = await cliente.get("/health")
                assert respuesta.status_code == 200

    async def test_un_datalake_ilegible_hace_fallar_el_arranque(
        self, tmp_path
    ) -> None:
        from app.datalake import DataLakeError

        rota = tmp_path / "rota.csv"
        rota.write_text("columna_inexistente\n2026-01-01\n", encoding="utf-8")
        app = construir_app(rota)
        with pytest.raises(DataLakeError):
            async for _ in abrir_cliente(app):
                pass


class TestSalud:
    """6.2: `/health` no toca ni Open-Meteo ni el Data Lake."""

    async def test_responde_ok(self, cliente: httpx.AsyncClient) -> None:
        respuesta = await cliente.get("/health")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"status": "ok"}

    async def test_es_exactamente_esa_forma(self, cliente: httpx.AsyncClient) -> None:
        assert list((await cliente.get("/health")).json().keys()) == ["status"]

    async def test_responde_ok_con_la_aplicacion_sin_datalake(
        self, ruta_csv_canonico: Path
    ) -> None:
        """`/health` se declara independiente del Data Lake: se rompe a propósito."""
        app = construir_app(ruta_csv_canonico)
        async for cliente in abrir_cliente(app):
            app.state.datalake = None
            app.state.clima = ClimaQueRevienta(WeatherUnavailableError("sin red"))
            respuesta = await cliente.get("/health")
            assert respuesta.status_code == 200
            assert respuesta.json() == {"status": "ok"}

    async def test_responde_ok_sin_ninguna_llamada_a_open_meteo(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            llamada = respx.get(url_open_meteo()).mock(
                return_value=respuesta_clima(date.today())
            )
            respuesta = await cliente.get("/health")
        assert respuesta.status_code == 200
        assert not llamada.called


class TestPrediccionExito:
    """6.3 y 7.3: camino feliz, forma exacta de la respuesta y contenido."""

    async def test_con_fecha_explicita(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        objetivo = hoy + timedelta(days=1)
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            respuesta = await cliente.get(
                "/api/prediction", params={"date": objetivo.isoformat()}
            )
        assert respuesta.status_code == 200
        assert respuesta.json()["target_date"] == objetivo.isoformat()

    async def test_sin_parametro_usa_la_fecha_de_hoy(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 200
        assert respuesta.json()["target_date"] == hoy.isoformat()

    async def test_la_respuesta_tiene_exactamente_las_claves_del_spec(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            cuerpo = (await cliente.get("/api/prediction")).json()
        assert set(cuerpo) == {"site", "target_date", "weather", "prediction"}
        assert set(cuerpo["weather"]) == {
            "temperature_max",
            "precipitation_probability",
            "condition",
        }
        assert set(cuerpo["prediction"]) == {
            "estimated_visitors",
            "capacity_percentage",
            "crowd_level",
        }
        assert cuerpo["site"] == "Machu Picchu"

    async def test_el_tipo_de_contenido_es_json(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(date.today()))
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("application/json")

    async def test_las_claves_coinciden_con_el_modelo_pydantic(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(date.today()))
            cuerpo = (await cliente.get("/api/prediction")).json()
        validado = RespuestaPrediccion.model_validate(cuerpo)
        assert validado.model_dump(mode="json") == cuerpo

    async def test_el_clima_condicionado_cambia_la_estimacion(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        objetivo = hoy + timedelta(days=1)
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            despejado = (
                await cliente.get("/api/prediction", params={"date": objetivo.isoformat()})
            ).json()
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=clima_tormenta(hoy))
            tormenta = (
                await cliente.get("/api/prediction", params={"date": objetivo.isoformat()})
            ).json()
        assert tormenta["weather"]["condition"] == "Tormenta"
        assert (
            tormenta["prediction"]["estimated_visitors"]
            < despejado["prediction"]["estimated_visitors"]
        )

    async def test_open_meteo_se_consume_una_sola_vez(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        with respx.mock:
            llamada = respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            respuesta = await cliente.get(
                "/api/prediction", params={"date": (hoy + timedelta(days=1)).isoformat()}
            )
        assert respuesta.status_code == 200
        assert llamada.call_count == 1

    async def test_el_nivel_se_deriva_de_las_cifras_publicadas(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy))
            cuerpo = (await cliente.get("/api/prediction")).json()
        estimados = cuerpo["prediction"]["estimated_visitors"]
        esperado = "Bajo" if estimados < 3000 else "Moderado" if estimados <= 4500 else "Alto"
        assert cuerpo["prediction"]["crowd_level"] == esperado


class TestPrediccionErrores:
    """6.3, 6.4 y 6.5: los tres 422 y el 502."""

    async def test_422_por_formato_invalido(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            llamada = respx.get(url_open_meteo()).mock(
                return_value=respuesta_clima(date.today())
            )
            respuesta = await cliente.get("/api/prediction", params={"date": "26-09-2026"})
        assert respuesta.status_code == 422
        assert "YYYY-MM-DD" in respuesta.json()["detail"]
        assert not llamada.called

    async def test_422_por_fecha_pasada(self, cliente: httpx.AsyncClient, hoy: date) -> None:
        with respx.mock:
            llamada = respx.get(url_open_meteo()).mock(
                return_value=respuesta_clima(hoy)
            )
            respuesta = await cliente.get(
                "/api/prediction", params={"date": (hoy - timedelta(days=1)).isoformat()}
            )
        assert respuesta.status_code == 422
        assert "pasó" in respuesta.json()["detail"]
        assert not llamada.called

    async def test_422_por_fecha_fuera_de_la_ventan_del_proveedor(
        self, cliente: httpx.AsyncClient, hoy: date
    ) -> None:
        objetivo = hoy + timedelta(days=9)
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=respuesta_clima(hoy, dias=3))
            respuesta = await cliente.get(
                "/api/prediction", params={"date": objetivo.isoformat()}
            )
        assert respuesta.status_code == 422
        ultima = (hoy + timedelta(days=2)).isoformat()
        assert ultima in respuesta.json()["detail"]

    async def test_502_cuando_open_meteo_no_responde(self, cliente: httpx.AsyncClient) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(side_effect=httpx.ReadTimeout("sin respuesta"))
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 502
        assert respuesta.status_code != 500
        detalle = respuesta.json()["detail"]
        assert "clima" in detalle.lower()
        assert "Traceback" not in detalle

    async def test_502_cuando_open_meteo_devuelve_error_de_estado(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(return_value=httpx.Response(500, text="boom"))
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 502

    async def test_502_cuando_el_payload_no_tiene_las_claves_esperadas(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(
                return_value=httpx.Response(200, json={"razon": "no"})
            )
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 502

    async def test_el_detalle_no_filtra_detalles_tecnicos(
        self, cliente: httpx.AsyncClient
    ) -> None:
        with respx.mock:
            respx.get(url_open_meteo()).mock(
                side_effect=httpx.ConnectError("DNS caído en api.inventada.local")
            )
            respuesta = await cliente.get("/api/prediction")
        assert respuesta.status_code == 502
        assert "api.inventada.local" not in respuesta.json()["detail"]


class TestCors:
    """6.6: los orígenes salen de la configuración, no de una lista en el router."""

    async def test_el_origen_permitido_recibe_cabeceras(self, cliente: httpx.AsyncClient) -> None:
        respuesta = await cliente.get(
            "/health", headers={"Origin": ORIGEN_PERMITIDO}
        )
        assert respuesta.status_code == 200
        assert respuesta.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO

    async def test_un_origen_no_permitido_no_recibe_cabeceras(
        self, cliente: httpx.AsyncClient
    ) -> None:
        respuesta = await cliente.get(
            "/health", headers={"Origin": ORIGEN_AHORA_RECHAZADO}
        )
        assert respuesta.status_code == 200
        assert "access-control-allow-origin" not in respuesta.headers

    async def test_el_preflight_de_la_prediccion(self, cliente: httpx.AsyncClient) -> None:
        respuesta = await cliente.options(
            "/api/prediction",
            headers={
                "Origin": ORIGEN_PERMITIDO,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert respuesta.status_code == 200
        assert respuesta.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO
        assert "GET" in respuesta.headers["access-control-allow-methods"]

    async def test_los_origenes_vienen_de_la_configuracion(self, hoy: date) -> None:
        app = construir_app(
            RUTA_POR_DEFECTO_DATALAKE,
            cors_origins=["https://otro.example"],
        )
        async for cliente in abrir_cliente(app):
            permitido = await cliente.get("/health", headers={"Origin": "https://otro.example"})
            rechazado = await cliente.get("/health", headers={"Origin": ORIGEN_PERMITIDO})
        assert permitido.headers.get("access-control-allow-origin") == "https://otro.example"
        assert "access-control-allow-origin" not in rechazado.headers


class TestConfiguracion:
    """6.7: la app arranca con los valores por omisión, sin variables de entorno."""

    def test_los_valores_por_omision_son_funcionales(self) -> None:
        ajustes = Settings()
        assert ajustes.ruta_datalake == RUTA_POR_DEFECTO_DATALAKE
        assert ajustes.ruta_datalake.is_file()
        assert ajustes.open_meteo_base_url.startswith("https://")
        assert ajustes.open_meteo_timeout > 0
        assert ajustes.cors_origins
        assert ajustes.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def test_se_puede_configurar_por_entorno(self, monkeypatch) -> None:
        monkeypatch.setenv("MP_RUTA_DATALAKE", "/tmp/otro.csv")
        monkeypatch.setenv("MP_OPEN_METEO_TIMEOUT", "9.5")
        monkeypatch.setenv("MP_LOG_LEVEL", "DEBUG")
        ajustes = Settings(_env_file=None)
        assert ajustes.ruta_datalake.as_posix() == "/tmp/otro.csv"
        assert ajustes.open_meteo_timeout == 9.5
        assert ajustes.log_level == "DEBUG"

    def test_el_log_nivel_se_normaliza(self) -> None:
        assert Settings(log_level="debug").log_level == "DEBUG"
        assert Settings(log_level="  Warning ").log_level == "WARNING"

    def test_un_nivel_de_log_inventado_falla_al_arrancar(self) -> None:
        with pytest.raises(PydanticValidationError, match="MP_LOG_LEVEL"):
            Settings(log_level="verboso")

    def test_un_nivel_de_log_que_no_es_texto_da_error_de_tipo(self) -> None:
        with pytest.raises(PydanticValidationError):
            Settings(log_level=None)

    def test_la_credencial_ausente_no_rompe_nada(self) -> None:
        assert "api_key" not in Settings.model_fields
        assert "open_meteo_api_key" not in Settings.model_fields

    def test_crear_app_acepta_configuracion_explicita(self) -> None:
        app = construir_app(RUTA_POR_DEFECTO_DATALAKE, log_level="DEBUG")
        assert isinstance(app, FastAPI)
        assert app.title

    def test_el_datalake_por_omision_carga(self) -> None:
        assert len(cargar_data_lake(Settings().ruta_datalake)) == 730


class TestContratoOpenapi:
    """6.8: el esquema publicado coincide con la superficie real."""

    async def test_openapi_responde_200(self, cliente: httpx.AsyncClient) -> None:
        respuesta = await cliente.get("/openapi.json")
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("application/json")

    async def test_declara_las_dos_rutas(self, cliente: httpx.AsyncClient) -> None:
        esquema = (await cliente.get("/openapi.json")).json()
        assert set(esquema["paths"]) >= {"/api/prediction", "/health"}

    async def test_la_ruta_de_prediccion_toma_un_parametro_opcional(
        self, cliente: httpx.AsyncClient
    ) -> None:
        esquema = (await cliente.get("/openapi.json")).json()
        parametros = esquema["paths"]["/api/prediction"]["get"]["parameters"]
        fecha = [p for p in parametros if p["name"] == "date"]
        assert len(fecha) == 1
        assert fecha[0]["in"] == "query"
        assert fecha[0]["required"] is False

    async def test_declara_los_modelos_de_respuesta(self, cliente: httpx.AsyncClient) -> None:
        esquema = (await cliente.get("/openapi.json")).json()
        assert "RespuestaPrediccion" in esquema["components"]["schemas"]

    async def test_la_documentacion_interactiva_esta_disponible(
        self, cliente: httpx.AsyncClient
    ) -> None:
        assert (await cliente.get("/docs")).status_code == 200
