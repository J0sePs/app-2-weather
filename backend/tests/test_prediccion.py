"""Lógica de predicción: clasificación, selección de días similares y niveles.

No hay red en ningún test: el clima entra como valor o como doble de la interfaz.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMA_DESPEJADO,
    CLIMA_LLUVIA,
    CLIMA_LLUVIA_TORRENCIAL,
    CLIMA_NUBLADO,
    CLIMA_TORMENTA,
    COLUMNAS,
    DataLake,
    DataLakeError,
    cargar_data_lake,
    es_fin_de_semana_o_feriado,
)
from app.prediction import (
    NIVEL_ALTO,
    NIVEL_BAJO,
    NIVEL_MODERADO,
    UMBRAL_ALTO,
    UMBRAL_MODERADO,
    ErrorPrediccion,
    Predictor,
    acotar_visitas,
    categoria_climatica,
    dias_similares,
    estimar_visitantes,
    nivel_afluencia,
    porcentaje_aforo,
)
from app.weather import Pronostico, PronosticoDiario
from tests.conftest import ClimaSimulado

#: Fechas de referencia: un sábado, un miércoles y dos feriados en día laborable.
SABADO = date(2026, 9, 26)
MIERCOLES = date(2026, 9, 30)
FERIADO_INT_RAYMI = date(2026, 6, 24)  # miércoles
FERIADO_INDEPENDENCIA = date(2026, 7, 28)  # martes


def pronostico(
    probabilidad: int = 0,
    codigo: int = 0,
    temperatura: float = 20.0,
    fecha: date = SABADO,
) -> PronosticoDiario:
    return PronosticoDiario(
        fecha=fecha,
        temperatura_max=temperatura,
        probabilidad_precipitacion=probabilidad,
        codigo_clima=codigo,
    )


class TestClasificacionDeFinDeSemanaOFeriado:
    """La predicción reutiliza el criterio y el catálogo del Data Lake."""

    def test_un_sabado(self) -> None:
        assert es_fin_de_semana_o_feriado(SABADO) is True

    def test_un_domingo(self) -> None:
        assert es_fin_de_semana_o_feriado(date(2026, 9, 27)) is True

    def test_inti_raymi(self) -> None:
        assert FERIADO_INT_RAYMI.weekday() < 5
        assert es_fin_de_semana_o_feriado(FERIADO_INT_RAYMI) is True

    def test_la_independencia(self) -> None:
        assert FERIADO_INDEPENDENCIA.weekday() < 5
        assert es_fin_de_semana_o_feriado(FERIADO_INDEPENDENCIA) is True

    def test_un_miercoles_ordinario(self) -> None:
        assert es_fin_de_semana_o_feriado(MIERCOLES) is False

    def test_la_clasificacion_coincide_con_la_marca_del_csv(
        self, registros
    ) -> None:
        for registro in registros:
            assert (
                es_fin_de_semana_o_feriado(registro.fecha)
                is registro.es_fin_de_semana_o_feriado
            )


class TestTraduccionDelClima:
    @pytest.mark.parametrize(
        ("probabilidad", "codigo", "esperado"),
        [
            (0, 0, CLIMA_DESPEJADO),
            (3, 0, CLIMA_DESPEJADO),
            (10, 3, CLIMA_NUBLADO),
            (30, 61, CLIMA_LLUVIA),
            (70, 63, CLIMA_LLUVIA_TORRENCIAL),
            (95, 80, CLIMA_TORMENTA),
            (100, 80, CLIMA_TORMENTA),
        ],
    )
    def test_las_bandas_de_probabilidad_mapean_al_vocabulario(
        self, probabilidad: int, codigo: int, esperado: str
    ) -> None:
        assert categoria_climatica(pronostico(probabilidad, codigo)) == esperado

    def test_la_lluvia_torrencial_no_se_compara_con_un_dia_despejado(self) -> None:
        assert categoria_climatica(pronostico(70, 65)) != CLIMA_DESPEJADO

    def test_la_tormenta_no_se_compara_con_un_dia_despejado(self) -> None:
        assert categoria_climatica(pronostico(95, 95)) != CLIMA_DESPEJADO

    def test_un_codigo_de_tormenta_manda_sobre_la_banda(self) -> None:
        """Un `weathercode` de tormenta con poca probabilidad sigue siendo tormenta."""
        assert categoria_climatica(pronostico(0, 95)) == CLIMA_TORMENTA
        assert categoria_climatica(pronostico(0, 96)) == CLIMA_TORMENTA
        assert categoria_climatica(pronostico(0, 99)) == CLIMA_TORMENTA

    def test_un_codigo_de_lluvia_intensa_sube_a_torrencial(self) -> None:
        assert categoria_climatica(pronostico(0, 65)) == CLIMA_LLUVIA_TORRENCIAL
        assert categoria_climatica(pronostico(30, 82)) == CLIMA_LLUVIA_TORRENCIAL

    def test_toda_la_escala_de_probabilidad_cae_en_el_vocabulario(self) -> None:
        for probabilidad in range(0, 101):
            assert categoria_climatica(pronostico(probabilidad, 3)) in {
                CLIMA_DESPEJADO,
                CLIMA_NUBLADO,
                CLIMA_LLUVIA,
                CLIMA_LLUVIA_TORRENCIAL,
                CLIMA_TORMENTA,
            }


class TestNivelDeAfluencia:
    @pytest.mark.parametrize(
        ("estimados", "esperado"),
        [
            (0, NIVEL_BAJO),
            (2400, NIVEL_BAJO),
            (UMBRAL_MODERADO - 1, NIVEL_BAJO),
            (UMBRAL_MODERADO, NIVEL_MODERADO),
            (UMBRAL_MODERADO + 1, NIVEL_MODERADO),
            (UMBRAL_ALTO - 1, NIVEL_MODERADO),
            (UMBRAL_ALTO, NIVEL_MODERADO),
            (UMBRAL_ALTO + 1, NIVEL_ALTO),
            (4580, NIVEL_ALTO),
            (CAPACIDAD_MAXIMA, NIVEL_ALTO),
        ],
    )
    def test_los_limites_exactos(self, estimados: int, esperado: str) -> None:
        assert nivel_afluencia(estimados) == esperado

    def test_los_umbrales_son_3000_y_4500(self) -> None:
        assert UMBRAL_MODERADO == 3000
        assert UMBRAL_ALTO == 4500

    @pytest.mark.parametrize(
        ("estimados", "esperado"),
        [(4580, 81.8), (5600, 100.0), (0, 0.0), (2400, 42.9), (3000, 53.6)],
    )
    def test_el_porcentaje_es_la_estimacion_sobre_5600(self, estimados: int, esperado: float) -> None:
        assert porcentaje_aforo(estimados) == esperado

    def test_el_porcentaje_tiene_un_decimal(self) -> None:
        valor = porcentaje_aforo(4580)
        assert isinstance(valor, float)
        assert len(str(valor).split(".")[1]) == 1

    def test_la_estimacion_se_acota_al_rango_del_sitio(self) -> None:
        assert acotar_visitas(-100) == 0
        assert acotar_visitas(0) == 0
        assert acotar_visitas(99999) == CAPACIDAD_MAXIMA
        assert acotar_visitas(3000.4) == 3000
        assert acotar_visitas(3000.6) == 3001

    def test_ninguna_estimacion_del_datalake_supera_el_aforo(
        self, data_lake_canonico: DataLake
    ) -> None:
        for fecha in (SABADO, MIERCOLES, FERIADO_INT_RAYMI):
            resultado = estimar_visitantes(
                data_lake_canonico, fecha, pronostico(fecha=fecha)
            )
            assert 0 <= resultado.estimados <= CAPACIDAD_MAXIMA


class TestSeleccionDeDiasSimilares:
    def test_el_criterio_estricto_es_el_clima(self, data_lake_canonico: DataLake) -> None:
        registros, criterio, categoria = dias_similares(
            data_lake_canonico, SABADO, pronostico(0, 0)
        )
        assert criterio == "clima"
        assert categoria == CLIMA_DESPEJADO
        assert registros
        assert all(r.clima == CLIMA_DESPEJADO for r in registros)
        assert all(r.es_fin_de_semana_o_feriado for r in registros)

    def test_el_nivel_estricto_respeta_la_condicion_de_fin_de_semana(
        self, data_lake_canonico: DataLake
    ) -> None:
        sabado, _, _ = dias_similares(data_lake_canonico, SABADO, pronostico(0, 0))
        miercoles, _, _ = dias_similares(data_lake_canonico, MIERCOLES, pronostico(0, 0))
        assert all(r.es_fin_de_semana_o_feriado for r in sabado)
        assert all(not r.es_fin_de_semana_o_feriado for r in miercoles)

    def test_relajado_cuando_el_clima_no_encuentra_coincidencias(
        self, escribir_csv
    ) -> None:
        """Sin ninguna coincidencia de clima, la estimación usa la temporada."""
        # Septiembre está en temporada seca, y el Data Lake de este test no tiene
        # ningún día de tormenta, así que el filtro estricto no encuentra nada.
        contenido = ",".join(COLUMNAS) + "\n" + "\n".join(
            [
                "2026-09-07,lunes,seca,lluvia,10.0,false,2000",
                "2026-09-14,lunes,seca,lluvia,11.0,false,2100",
                "2026-09-21,lunes,seca,nublado,12.0,false,2200",
            ]
        ) + "\n"
        data_lake = cargar_data_lake(escribir_csv("sin-tormenta.csv", contenido))

        registros, criterio, categoria = dias_similares(
            data_lake, MIERCOLES, pronostico(95, 95, fecha=MIERCOLES)
        )
        assert categoria == CLIMA_TORMENTA
        assert criterio == "temporada"
        assert registros
        assert all(r.temporada == "seca" for r in registros)

        resultado = estimar_visitantes(data_lake, MIERCOLES, pronostico(95, 95, fecha=MIERCOLES))
        assert resultado.criterio == "temporada"
        assert resultado.estimados == 2100
        assert 0 <= resultado.estimados <= CAPACIDAD_MAXIMA

    def test_relajado_tambien_respeta_la_condicion_de_fin_de_semana(
        self, escribir_csv
    ) -> None:
        contenido = ",".join(COLUMNAS) + "\n" + "\n".join(
            [
                "2026-09-07,lunes,seca,lluvia,10.0,false,2000",
                "2026-09-05,sábado,seca,lluvia,10.0,true,2800",
            ]
        ) + "\n"
        data_lake = cargar_data_lake(escribir_csv("relajado.csv", contenido))

        registros, criterio, _ = dias_similares(
            data_lake, SABADO, pronostico(95, 95, fecha=SABADO)
        )
        assert criterio == "temporada"
        assert [r.visitantes_reales for r in registros] == [2800]

    def test_sin_coincidencias_tampoco_relajadas_no_hay_estimacion(
        self, escribir_csv
    ) -> None:
        contenido = ",".join(COLUMNAS) + "\n2026-01-05,lunes,lluvias,lluvia,10.0,false,2000\n"
        data_lake = cargar_data_lake(escribir_csv("vacio.csv", contenido))
        with pytest.raises(ErrorPrediccion):
            estimar_visitantes(data_lake, SABADO, pronostico(95, 95, fecha=SABADO))


class TestOrdenacionesDeLaEstimacion:
    def test_un_sabado_seco_estima_por_encima_de_un_miercoles_seco(
        self, data_lake_canonico: DataLake
    ) -> None:
        sabado = estimar_visitantes(data_lake_canonico, SABADO, pronostico(0, 0, fecha=SABADO))
        miercoles = estimar_visitantes(
            data_lake_canonico, MIERCOLES, pronostico(0, 0, fecha=MIERCOLES)
        )
        assert sabado.estimados > miercoles.estimados

    def test_un_dia_de_tormenta_estima_por_debajo(
        self, data_lake_canonico: DataLake
    ) -> None:
        tormenta = estimar_visitantes(
            data_lake_canonico, MIERCOLES, pronostico(95, 95, fecha=MIERCOLES)
        )
        despejado = estimar_visitantes(
            data_lake_canonico, MIERCOLES, pronostico(0, 0, fecha=MIERCOLES)
        )
        assert tormenta.estimados < despejado.estimados

    def test_un_feriado_en_dia_laborable_estima_por_encima(
        self, data_lake_canonico: DataLake
    ) -> None:
        laborable = estimar_visitantes(
            data_lake_canonico, MIERCOLES, pronostico(0, 0, fecha=MIERCOLES)
        )
        for feriado in (FERIADO_INT_RAYMI, FERIADO_INDEPENDENCIA):
            festivo = estimar_visitantes(
                data_lake_canonico, feriado, pronostico(0, 0, fecha=feriado)
            )
            assert festivo.estimados > laborable.estimados

    def test_la_lluvia_torrencial_estima_por_debajo_de_la_lluvia_normal(
        self, data_lake_canonico: DataLake
    ) -> None:
        normal = estimar_visitantes(data_lake_canonico, MIERCOLES, pronostico(30, 61, fecha=MIERCOLES))
        torrencial = estimar_visitantes(
            data_lake_canonico, MIERCOLES, pronostico(70, 65, fecha=MIERCOLES)
        )
        assert torrencial.estimados < normal.estimados

    def test_la_estimacion_es_el_promedio_de_los_registros_elegidos(
        self, data_lake_canonico: DataLake
    ) -> None:
        registros, criterio, _ = dias_similares(data_lake_canonico, SABADO, pronostico(0, 0))
        esperado = sum(r.visitantes_reales for r in registros) / len(registros)
        resultado = estimar_visitantes(data_lake_canonico, SABADO, pronostico(0, 0))
        assert criterio == "clima"
        assert resultado.estimados == round(esperado)
        assert resultado.registros_similares == len(registros)


class TestPredictorConDobleDeClima:
    async def test_consulta_el_clima_una_sola_vez(self, data_lake_canonico: DataLake) -> None:
        clima = ClimaSimulado({SABADO: pronostico(0, 0, fecha=SABADO)})
        predictor = Predictor(data_lake_canonico)
        resultado = await predictor.predecir(SABADO, clima)
        assert clima.llamadas == 1
        assert resultado.fecha == SABADO
        assert resultado.estimados > 0

    async def test_el_resultado_lleva_el_clima_del_dia(
        self, data_lake_canonico: DataLake
    ) -> None:
        clima = ClimaSimulado({SABADO: pronostico(0, 0, temperatura=23.5, fecha=SABADO)})
        resultado = await Predictor(data_lake_canonico).predecir(SABADO, clima)
        assert resultado.pronostico.temperatura_max == 23.5
        assert resultado.pronostico.condicion == "Despejado"

    async def test_una_fecha_fuera_del_pronostico_lanza_error(
        self, data_lake_canonico: DataLake
    ) -> None:
        clima = ClimaSimulado({SABADO: pronostico(0, 0, fecha=SABADO)})
        with pytest.raises(KeyError):
            await Predictor(data_lake_canonico).predecir(MIERCOLES, clima)

    def test_estimar_usa_un_pronostico_ya_obtenido(
        self, data_lake_canonico: DataLake
    ) -> None:
        pronosticos = Pronostico(por_fecha={SABADO: pronostico(0, 0, fecha=SABADO)})
        resultado = Predictor(data_lake_canonico).estimar(SABADO, pronosticos)
        assert resultado.fecha == SABADO
        assert resultado.estimados > 0

    def test_el_resultado_expone_el_criterio_usado(
        self, data_lake_canonico: DataLake
    ) -> None:
        resultado = estimar_visitantes(data_lake_canonico, SABADO, pronostico(0, 0))
        assert resultado.criterio in {"clima", "temporada"}
        assert resultado.categoria_clima in {
            CLIMA_DESPEJADO,
            CLIMA_NUBLADO,
            CLIMA_LLUVIA,
            CLIMA_LLUVIA_TORRENCIAL,
            CLIMA_TORMENTA,
        }
        assert resultado.temporada in {"seca", "lluvias"}
        assert resultado.es_fin_de_semana_o_feriado is True
        assert isinstance(resultado.porcentaje_aforo, float)
