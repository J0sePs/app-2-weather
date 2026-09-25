"""Calendario, vocabulario y catálogo de feriados del Data Lake.

Cubre el requisito de generation del Data Lake: funciones de fecha en español, día de
la semana, temporada, clima y catálogo de feriados.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMAS,
    CLIMAS_MAL_TIEMPO,
    COLUMNAS,
    DIAS_SEMANA,
    FERIADOS_PERUANOS,
    TEMPORADA_LLUVIAS,
    TEMPORADA_SECA,
    TEMPORADAS,
    es_buen_tiempo,
    es_feriado,
    es_fin_de_semana_o_feriado,
    fecha_en_espanol,
    feriado_de,
    nombre_dia_semana,
    nombre_mes,
    temporada_de,
    texto_booleano,
)


class TestVocabulario:
    def test_los_dias_de_la_semana_estan_en_espanol(self) -> None:
        assert DIAS_SEMANA == (
            "lunes",
            "martes",
            "miércoles",
            "jueves",
            "viernes",
            "sábado",
            "domingo",
        )

    def test_las_temporadas_son_dos(self) -> None:
        assert TEMPORADAS == (TEMPORADA_SECA, TEMPORADA_LLUVIAS)

    def test_las_categorias_climaticas_son_las_cinco_del_vocabulario_fijo(self) -> None:
        assert CLIMAS == (
            "despejado",
            "nublado",
            "lluvia",
            "lluvia_torrencial",
            "tormenta",
        )

    def test_el_mal_tiempo_son_lluvia_torrencial_y_tormenta(self) -> None:
        assert CLIMAS_MAL_TIEMPO == {"lluvia_torrencial", "tormenta"}

    def test_el_esquema_tiene_las_columnas_en_el_orden_definido(self) -> None:
        assert COLUMNAS == (
            "fecha",
            "dia_semana",
            "temporada",
            "clima",
            "temperatura_c",
            "es_fin_de_semana_o_feriado",
            "visitantes_reales",
        )

    def test_la_capacidad_maxima_es_5600(self) -> None:
        assert CAPACIDAD_MAXIMA == 5600


class TestNombreDiaSemana:
    @pytest.mark.parametrize(
        ("fecha", "esperado"),
        [
            (date(2026, 6, 28), "domingo"),
            (date(2026, 6, 27), "sábado"),
            (date(2026, 6, 24), "miércoles"),
            (date(2026, 7, 28), "martes"),
            (date(2026, 1, 1), "jueves"),
        ],
    )
    def test_devuelve_el_dia_en_espanol(self, fecha: date, esperado: str) -> None:
        assert nombre_dia_semana(fecha) == esperado

    def test_cubre_los_siete_dias_a_partir_del_lunes(self) -> None:
        lunes = date(2026, 6, 22)
        nombres = [nombre_dia_semana(lunes.fromordinal(lunes.toordinal() + i)) for i in range(7)]
        assert nombres == list(DIAS_SEMANA)


class TestFechaEnEspanol:
    def test_formatea_la_fecha_en_espanol(self) -> None:
        assert fecha_en_espanol(date(2026, 6, 24)) == "24 de junio de 2026"

    def test_el_nombre_del_mes_esta_en_espanol(self) -> None:
        assert nombre_mes(date(2026, 12, 31)) == "diciembre"
        assert nombre_mes(date(2026, 1, 1)) == "enero"


class TestTemporada:
    @pytest.mark.parametrize("mes", [5, 6, 7, 8, 9, 10])
    def test_mayo_a_octubre_es_temporada_seca(self, mes: int) -> None:
        assert temporada_de(date(2026, mes, 15)) == TEMPORADA_SECA

    @pytest.mark.parametrize("mes", [11, 12, 1, 2, 3, 4])
    def test_noviembre_a_abril_es_temporada_de_lluvias(self, mes: int) -> None:
        assert temporada_de(date(2026, mes, 15)) == TEMPORADA_LLUVIAS

    def test_abril_da_lluvias(self) -> None:
        assert temporada_de(date(2026, 4, 30)) == TEMPORADA_LLUVIAS

    def test_todos_los_meses_caen_en_alguna_temporada(self) -> None:
        for mes in range(1, 13):
            assert temporada_de(date(2026, mes, 1)) in TEMPORADAS


class TestCatalogoDeFeriados:
    def test_el_catalogo_es_un_dato_fijo_del_codigo(self) -> None:
        assert len(FERIADOS_PERUANOS) >= 2
        assert all(1 <= f.mes <= 12 and 1 <= f.dia <= 31 for f in FERIADOS_PERUANOS)

    @pytest.mark.parametrize(
        "fecha",
        [date(2026, 6, 24), date(2026, 7, 28)],
    )
    def test_los_feriados_de_referencia_estan_en_el_catalogo(self, fecha: date) -> None:
        assert es_feriado(fecha) is True
        assert feriado_de(fecha) is not None

    def test_inti_raymi_esta_nombrado(self) -> None:
        assert feriado_de(date(2026, 6, 24)).nombre == "Inti Raymi"

    def test_la_independencia_esta_nombrada(self) -> None:
        assert feriado_de(date(2026, 7, 28)).nombre == "Fiesta de la Independencia"

    def test_un_dia_ordinario_no_es_feriado(self) -> None:
        assert es_feriado(date(2026, 9, 16)) is False
        assert feriado_de(date(2026, 9, 16)) is None


class TestEsFinDeSemanaOFeriado:
    def test_un_sabado(self) -> None:
        assert es_fin_de_semana_o_feriado(date(2026, 6, 27)) is True

    def test_un_domingo(self) -> None:
        assert es_fin_de_semana_o_feriado(date(2026, 6, 28)) is True

    def test_un_feriado_en_dia_laborable(self) -> None:
        assert date(2026, 6, 24).weekday() < 5
        assert es_fin_de_semana_o_feriado(date(2026, 6, 24)) is True

    def test_un_miercoles_ordinario(self) -> None:
        assert es_fin_de_semana_o_feriado(date(2026, 9, 16)) is False

    def test_es_estable_entre_llamadas(self) -> None:
        fecha = date(2026, 7, 28)
        assert es_fin_de_semana_o_feriado(fecha) == es_fin_de_semana_o_feriado(fecha)


class TestAuxiliares:
    def test_texto_booleano_usa_true_y_false(self) -> None:
        assert texto_booleano(True) == "true"
        assert texto_booleano(False) == "false"

    def test_es_buen_tiempo_excluye_el_mal_tiempo(self) -> None:
        assert es_buen_tiempo("despejado") is True
        assert es_buen_tiempo("nublado") is True
        assert es_buen_tiempo("lluvia") is True
        assert es_buen_tiempo("lluvia_torrencial") is False
        assert es_buen_tiempo("tormenta") is False
