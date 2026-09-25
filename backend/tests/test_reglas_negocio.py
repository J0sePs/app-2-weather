"""Reglas de negocio del Data Lake, leídas del CSV canónico versionado.

Estos tests no usan fixtures duplicadas: leen el mismo archivo que consume el backend,
de modo que un cambio en el generador sin regenerar el CSV se convierte en un fallo
visible de la suite.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMAS_MAL_TIEMPO,
    COLUMNAS,
    DIAS_LABORABLES,
    TEMPORADA_LLUVIAS,
    TEMPORADA_SECA,
    es_buen_tiempo,
    es_fin_de_semana_o_feriado,
    promedio_visitantes,
)

DIAS_DEL_HISTORIAL = 730


class TestEsquemaDelArchivo:
    def test_la_primera_linea_es_el_encabezado_definido(self, ruta_csv_canonico: Path) -> None:
        encabezado = ruta_csv_canonico.read_text(encoding="utf-8").splitlines()[0]
        assert encabezado == ",".join(COLUMNAS)

    def test_todas_las_filas_tienen_siete_campos(self, ruta_csv_canonico: Path) -> None:
        lineas = ruta_csv_canonico.read_text(encoding="utf-8").splitlines()
        for linea in lineas[1:]:
            assert len(linea.split(",")) == 7, linea

    def test_el_archivo_usa_salto_de_linea_unix(self, ruta_csv_canonico: Path) -> None:
        assert "\r" not in ruta_csv_canonico.read_text(encoding="utf-8")


class TestCoberturaDelHistorial:
    def test_tiene_730_registros(self, data_lake_canonico) -> None:
        assert len(data_lake_canonico) == DIAS_DEL_HISTORIAL

    def test_las_fechas_son_consecutivas_sin_huecos_ni_duplicados(
        self, data_lake_canonico
    ) -> None:
        inicio, fin = data_lake_canonico.rango_fechas
        assert (fin - inicio).days == DIAS_DEL_HISTORIAL - 1

        fechas = [registro.fecha for registro in data_lake_canonico]
        assert len(set(fechas)) == DIAS_DEL_HISTORIAL
        for anterior, siguiente in zip(fechas, fechas[1:], strict=False):
            assert siguiente - anterior == timedelta(days=1)


class TestAforoOficial:
    def test_ningun_registro_excede_la_capacidad_maxima(self, registros) -> None:
        maximo = max(registro.visitantes_reales for registro in registros)
        assert maximo <= CAPACIDAD_MAXIMA

    def test_no_hay_visitantes_negativos(self, registros) -> None:
        assert all(registro.visitantes_reales >= 0 for registro in registros)


class TestTemporadas:
    def test_la_media_seca_supera_a_la_lluvias_en_al_menos_1000(self, data_lake_canonico) -> None:
        seca = promedio_visitantes(data_lake_canonico.filtrar(temporadas={TEMPORADA_SECA}))
        lluvias = promedio_visitantes(
            data_lake_canonico.filtrar(temporadas={TEMPORADA_LLUVIAS})
        )
        assert seca is not None and lluvias is not None
        assert seca - lluvias >= 1000

    def test_los_dias_laborables_de_buen_tiempo_cumplen_los_rangos(
        self, data_lake_canonico
    ) -> None:
        base = data_lake_canonico.filtrar(fin_de_semana_o_feriado=False)
        seca = [
            registro.visitantes_reales
            for registro in base
            if registro.temporada == TEMPORADA_SECA and es_buen_tiempo(registro.clima)
        ]
        lluvias = [
            registro.visitantes_reales
            for registro in base
            if registro.temporada == TEMPORADA_LLUVIAS and es_buen_tiempo(registro.clima)
        ]

        assert seca, "el CSV debe tener días laborables de buen tiempo en temporada seca"
        assert lluvias, "el CSV debe tener días laborables de buen tiempo en temporada de lluvias"
        assert min(seca) >= 4000 and max(seca) <= 5200
        assert min(lluvias) >= 1800 and max(lluvias) <= 3200

    def test_la_temporada_seca_es_mas_calida_que_la_de_lluvias(self, registros) -> None:
        seca = [r.temperatura_c for r in registros if r.temporada == TEMPORADA_SECA]
        lluvias = [r.temperatura_c for r in registros if r.temporada == TEMPORADA_LLUVIAS]
        assert sum(seca) / len(seca) > sum(lluvias) / len(lluvias)

    def test_las_temperaturas_son_plausibles_para_la_zona(self, registros) -> None:
        assert all(5.0 <= r.temperatura_c <= 28.0 for r in registros)

    def test_la_marca_de_temporada_corresponde_al_mes(self, registros) -> None:
        for registro in registros:
            esperada = (
                TEMPORADA_SECA
                if registro.fecha.month in {5, 6, 7, 8, 9, 10}
                else TEMPORADA_LLUVIAS
            )
            assert registro.temporada == esperada


class TestMalTiempo:
    @pytest.mark.parametrize("temporada", [TEMPORADA_SECA, TEMPORADA_LLUVIAS])
    @pytest.mark.parametrize("fin_de_semana", [True, False])
    def test_el_mal_tiempo_esta_por_deajo_del_buen_tiempo(
        self, data_lake_canonico, temporada: str, fin_de_semana: bool
    ) -> None:
        seleccionado = data_lake_canonico.filtrar(
            temporadas={temporada}, fin_de_semana_o_feriado=fin_de_semana
        )
        mal = promedio_visitantes([r for r in seleccionado if r.clima in CLIMAS_MAL_TIEMPO])
        bien = promedio_visitantes([r for r in seleccionado if es_buen_tiempo(r.clima)])

        assert mal is not None, "el CSV debe tener días de mal tiempo en cada temporada"
        assert bien is not None
        assert mal < bien

    def test_el_csv_incluye_las_cinco_categorias_climaticas(self, registros) -> None:
        assert {registro.clima for registro in registros} == {
            "despejado",
            "nublado",
            "lluvia",
            "lluvia_torrencial",
            "tormenta",
        }


class TestFinDeSemanaYFeriados:
    def test_el_fin_de_semana_agrupa_sabados_domingos_y_feriados(self, data_lake_canonico) -> None:
        marcados = data_lake_canonico.filtrar(fin_de_semana_o_feriado=True)
        assert all(registro.es_fin_de_semana_o_feriado for registro in marcados)

        dias = {registro.dia_semana for registro in marcados}
        assert {"sábado", "domingo"} <= dias
        assert any(d not in DIAS_LABORABLES for d in dias), (
            "debe haber al menos un feriado que caiga de lunes a viernes"
        )

    def test_los_no_marcados_no_son_sabado_domingo_ni_feriado(self, registros) -> None:
        for registro in registros:
            if not registro.es_fin_de_semana_o_feriado:
                assert registro.dia_semana in DIAS_LABORABLES
                assert es_fin_de_semana_o_feriado(registro.fecha) is False

    def test_la_marca_coincide_con_el_criterio_del_calendario(self, registros) -> None:
        for registro in registros:
            esperado = es_fin_de_semana_o_feriado(registro.fecha)
            assert registro.es_fin_de_semana_o_feriado is esperado, registro.fecha

    def test_todo_feriado_del_rango_esta_marcado_como_afluencia_alta(self, registros) -> None:
        for registro in registros:
            if registro.dia_semana not in DIAS_LABORABLES:
                continue
            if not es_fin_de_semana_o_feriado(registro.fecha):
                continue
            assert registro.es_fin_de_semana_o_feriado is True, registro.fecha

    @pytest.mark.parametrize("temporada", [TEMPORADA_SECA, TEMPORADA_LLUVIAS])
    def test_los_feriados_en_dia_laborable_elevan_la_afluencia(
        self, data_lake_canonico, temporada: str
    ) -> None:
        de_temporada = [
            registro
            for registro in data_lake_canonico.filtrar(temporadas={temporada})
            if registro.dia_semana in DIAS_LABORABLES
        ]
        feriados = [r for r in de_temporada if r.es_fin_de_semana_o_feriado]
        laborables = [r for r in de_temporada if not r.es_fin_de_semana_o_feriado]

        assert feriados, f"debe haber feriados en día laborable de temporada {temporada}"
        assert promedio_visitantes(feriados) > promedio_visitantes(laborables)

    def test_el_conjunto_marcado_tiene_mas_afluencia_que_el_no_marcado(
        self, data_lake_canonico
    ) -> None:
        marcados = promedio_visitantes(data_lake_canonico.filtrar(fin_de_semana_o_feriado=True))
        no_marcados = promedio_visitantes(
            data_lake_canonico.filtrar(fin_de_semana_o_feriado=False)
        )
        assert marcados > no_marcados


class TestVocabularyCoherente:
    def test_el_dia_semana_registrado_coincide_con_la_fecha(self, registros) -> None:
        from app.datalake import nombre_dia_semana

        for registro in registros:
            assert registro.dia_semana == nombre_dia_semana(registro.fecha)

    def test_las_temperaturas_tienen_un_decimal_en_el_csv(self, ruta_csv_canonico: Path) -> None:
        lineas = ruta_csv_canonico.read_text(encoding="utf-8").splitlines()[1:]
        for linea in lineas[:50]:
            temperatura = linea.split(",")[4]
            assert "." in temperatura and len(temperatura.split(".")[1]) == 1

    def test_las_visitas_son_enteras_en_el_csv(self, ruta_csv_canonico: Path) -> None:
        lineas = ruta_csv_canonico.read_text(encoding="utf-8").splitlines()[1:]
        for linea in lineas:
            visitantes = linea.split(",")[6]
            assert visitantes.isdigit()

    def test_las_booleanas_usan_true_y_false(self, ruta_csv_canonico: Path) -> None:
        lineas = ruta_csv_canonico.read_text(encoding="utf-8").splitlines()[1:]
        valores = {linea.split(",")[5] for linea in lineas}
        assert valores <= {"true", "false"}
        assert valores == {"true", "false"}


class TestCoberturaDelRango:
    def test_el_rango_cubre_todo_el_ano_2026(self, data_lake_canonico) -> None:
        inicio, fin = data_lake_canonico.rango_fechas
        assert inicio == date(2025, 1, 1)
        assert fin == date(2026, 12, 31)
