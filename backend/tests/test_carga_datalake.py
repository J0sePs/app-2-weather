"""Carga y consulta del Data Lake: validación de encabezados, archivo ausente y filtros.

Para los casos de error se usan CSV en línea mínimos; para las consultas se usa el CSV
canónico versionado.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.datalake import (
    COLUMNAS,
    COMANDO_GENERADOR,
    DataLake,
    DataLakeError,
    TEMPORADA_SECA,
    TEMPORADA_LLUVIAS,
    cargar_data_lake,
    promedio_visitantes,
)

ENCABEZADO = ",".join(COLUMNAS)

CSV_VALIDO = (
    f"{ENCABEZADO}\n"
    "2025-06-02,lunes,seca,despejado,22.5,false,4500\n"
    "2025-06-07,sábado,seca,despejado,23.0,true,5200\n"
    "2025-06-28,sábado,seca,lluvia_torrencial,15.0,true,2000\n"
    "2026-01-15,jueves,lluvias,nublado,12.0,false,2200\n"
)


class TestCargaDelArchivo:
    def test_carga_un_csv_valido(self, escribir_csv) -> None:
        ruta = escribir_csv("ok.csv", CSV_VALIDO)
        data_lake = cargar_data_lake(ruta)
        assert len(data_lake) == 4
        assert data_lake.ruta == ruta

    def test_sin_argumento_usa_la_ruta_por_defecto(self, monkeypatch) -> None:
        """La carga sin argumento apunta al CSV canónico del proyecto."""
        monkeypatch.setattr("app.datalake.RUTA_POR_DEFECTO_DATALAKE", Path("/no/existe.csv"))
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake()
        assert "/no/existe.csv" in str(error.value)

    def test_lee_el_csv_una_sola_vez(self, escribir_csv, monkeypatch) -> None:
        ruta = escribir_csv("una-vez.csv", CSV_VALIDO)
        llamadas = {"n": 0}
        abierto_original = Path.open

        def contando(self, *args, **kwargs):
            if self == ruta:
                llamadas["n"] += 1
            return abierto_original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", contando)
        data_lake = cargar_data_lake(ruta)
        llamadas["n"] = 0
        for _ in range(20):
            data_lake.filtrar(temporadas={TEMPORADA_SECA})
            data_lake.por_fecha(date(2025, 6, 2))
        assert llamadas["n"] == 0

    def test_registro_tiene_los_campos_del_esquema(self, escribir_csv) -> None:
        data_lake = cargar_data_lake(escribir_csv("ok.csv", CSV_VALIDO))
        registro = data_lake.por_fecha(date(2025, 6, 7))[0]
        assert registro.fecha == date(2025, 6, 7)
        assert registro.dia_semana == "sábado"
        assert registro.temporada == TEMPORADA_SECA
        assert registro.clima == "despejado"
        assert registro.temperatura_c == 23.0
        assert registro.es_fin_de_semana_o_feriado is True
        assert registro.visitantes_reales == 5200

    def test_el_rango_de_fechas_abarca_el_historial(self, escribir_csv) -> None:
        data_lake = cargar_data_lake(escribir_csv("ok.csv", CSV_VALIDO))
        assert data_lake.rango_fechas == (date(2025, 6, 2), date(2026, 1, 15))

    def test_un_csv_sin_filas_da_error(self, escribir_csv) -> None:
        ruta = escribir_csv("vacio.csv", f"{ENCABEZADO}\n")
        with pytest.raises(DataLakeError, match="no tiene filas de datos"):
            cargar_data_lake(ruta)


class TestEncabezadoInvalido:
    def test_una_columna_faltante_nombra_la_columna(self, escribir_csv) -> None:
        ruta = escribir_csv(
            "falta.csv",
            "fecha,dia_semana,temporada,clima,temperatura_c,visitantes_reales\n"
            "2025-06-02,lunes,seca,despejado,22.5,4500\n",
        )
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake(ruta)
        mensaje = str(error.value)
        assert "es_fin_de_semana_o_feriado" in mensaje
        assert "faltan las columnas" in mensaje

    def test_una_columna_sobrante_se_reporta(self, escribir_csv) -> None:
        ruta = escribir_csv(
            "sobra.csv",
            f"{ENCABEZADO},columna_inventada\n2025-06-02,lunes,seca,despejado,22.5,false,4500,1\n",
        )
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake(ruta)
        mensaje = str(error.value)
        assert "sobran las columnas" in mensaje
        assert "columna_inventada" in mensaje

    def test_un_orden_distinto_de_columnas_se_reporta(self, escribir_csv) -> None:
        ruta = escribir_csv(
            "orden.csv",
            "dia_semana,fecha,temporada,clima,temperatura_c,"
            "es_fin_de_semana_o_feriado,visitantes_reales\n"
            "lunes,2025-06-02,seca,despejado,22.5,false,4500\n",
        )
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake(ruta)
        assert "orden de las columnas" in str(error.value)

    def test_el_error_nombra_la_ruta_del_archivo(self, escribir_csv) -> None:
        ruta = escribir_csv("nombre.csv", "fecha\n2025-06-02\n")
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake(ruta)
        assert "nombre.csv" in str(error.value)


class TestValoresInvalidos:
    @pytest.mark.parametrize(
        ("contenido", "esperado"),
        [
            (
                f"{ENCABEZADO}\n2025-13-45,lunes,seca,despejado,22.5,false,4500\n",
                "fecha inválida",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,lunes,seca,neblina,22.5,false,4500\n",
                "no está en el vocabulario",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,lunes,verano,despejado,22.5,false,4500\n",
                "no está en el vocabulario",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,funday,seca,despejado,22.5,false,4500\n",
                "no está en el vocabulario",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,lunes,seca,despejado,22.5,quizá,4500\n",
                "no es un booleano",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,lunes,seca,despejado,calor,false,4500\n",
                "no numérico",
            ),
            (
                f"{ENCABEZADO}\n2025-06-02,lunes,seca,despejado,22.5,false,-10\n",
                "negativo",
            ),
        ],
    )
    def test_valores_fuera_de_vocabulario_dan_error(
        self, escribir_csv, contenido: str, esperado: str
    ) -> None:
        ruta = escribir_csv("invalido.csv", contenido)
        with pytest.raises(DataLakeError, match=esperado):
            cargar_data_lake(ruta)

    def test_una_fila_truncada_da_error_en_vez_de_una_excepcion_opaca(
        self, escribir_csv
    ) -> None:
        """Una fila a la que le faltan columnas debe fallar con un mensaje utilizable."""
        ruta = escribir_csv(
            "truncada.csv", f"{ENCABEZADO}\n2025-06-02,lunes,seca\n"
        )
        with pytest.raises(DataLakeError, match="truncada") as info:
            cargar_data_lake(ruta)
        assert "visitantes_reales" in str(info.value)

    def test_una_fila_con_columnas_de_mas_da_error(
        self, escribir_csv
    ) -> None:
        """Una columna extra rompe el esquema declarado y no se ignora en silencio."""
        ruta = escribir_csv(
            "sobrante.csv",
            f"{ENCABEZADO}\n2025-06-02,lunes,seca,despejado,22.5,false,4500,extra\n",
        )
        with pytest.raises(DataLakeError, match="columna"):
            cargar_data_lake(ruta)


class TestArchivoAusente:
    def test_una_ruta_inexistente_da_error(self, tmp_path: Path) -> None:
        ruta = tmp_path / "no_existe.csv"
        with pytest.raises(DataLakeError) as error:
            cargar_data_lake(ruta)
        mensaje = str(error.value)
        assert str(ruta) in mensaje, "el error debe nombrar la ruta que no pudo cargar"
        assert COMANDO_GENERADOR in mensaje, "el error debe sugerir el comando del generador"

    def test_un_directorio_no_es_un_data_lake(self, tmp_path: Path) -> None:
        with pytest.raises(DataLakeError, match=str(tmp_path)):
            cargar_data_lake(tmp_path)

    def test_el_error_nunca_sustituye_por_un_conjunto_vacio(self, tmp_path: Path) -> None:
        with pytest.raises(DataLakeError):
            cargar_data_lake(tmp_path / "ausente.csv")


class TestFiltros:
    def test_filtro_por_dias_de_la_semana(self, data_lake_canonico: DataLake) -> None:
        resultados = data_lake_canonico.filtrar(dias_semana={"sábado", "domingo"})
        assert resultados
        assert {r.dia_semana for r in resultados} == {"sábado", "domingo"}
        assert len(resultados) < len(data_lake_canonico)

    def test_filtro_por_categorias_climaticas(self, data_lake_canonico: DataLake) -> None:
        resultados = data_lake_canonico.filtrar(climas={"despejado", "nublado"})
        assert resultados
        assert {r.clima for r in resultados} <= {"despejado", "nublado"}
        assert len(resultados) < len(data_lake_canonico)

    def test_filtro_por_temporada(self, data_lake_canonico: DataLake) -> None:
        resultados = data_lake_canonico.filtrar(temporadas={TEMPORADA_SECA})
        assert resultados
        assert {r.temporada for r in resultados} == {TEMPORADA_SECA}
        assert len(resultados) < len(data_lake_canonico)

    def test_filtro_por_condicion_de_fin_de_semana_o_feriado(
        self, data_lake_canonico: DataLake
    ) -> None:
        resultados = data_lake_canonico.filtrar(fin_de_semana_o_feriado=True)
        assert all(r.es_fin_de_semana_o_feriado for r in resultados)
        assert "sábado" in {r.dia_semana for r in resultados}
        assert "domingo" in {r.dia_semana for r in resultados}
        assert any(r.dia_semana not in {"sábado", "domingo"} for r in resultados), (
            "el conjunto debe incluir también feriados en día laborable"
        )

    def test_la_media_del_conjunto_marcado_supera_a_la_del_no_marcado(
        self, data_lake_canonico: DataLake
    ) -> None:
        marcados = promedio_visitantes(
            data_lake_canonico.filtrar(fin_de_semana_o_feriado=True)
        )
        no_marcados = promedio_visitantes(
            data_lake_canonico.filtrar(fin_de_semana_o_feriado=False)
        )
        assert marcados > no_marcados

    def test_filtro_por_fecha_exacta(self, data_lake_canonico: DataLake) -> None:
        resultados = data_lake_canonico.por_fecha(date(2026, 6, 24))
        assert len(resultados) == 1
        assert resultados[0].fecha == date(2026, 6, 24)

    def test_por_fecha_devuelve_lista_vacia_si_no_esta_en_el_rango(
        self, data_lake_canonico: DataLake
    ) -> None:
        assert data_lake_canonico.por_fecha(date(2020, 1, 1)) == []

    def test_sin_filtros_devuelve_todo(self, data_lake_canonico: DataLake) -> None:
        assert len(data_lake_canonico.filtrar()) == len(data_lake_canonico)

    def test_los_filtros_se_combinan(self, data_lake_canonico: DataLake) -> None:
        resultados = data_lake_canonico.filtrar(
            dias_semana={"sábado"},
            climas={"despejado"},
            temporadas={TEMPORADA_SECA},
            fin_de_semana_o_feriado=True,
        )
        assert resultados
        for registro in resultados:
            assert registro.dia_semana == "sábado"
            assert registro.clima == "despejado"
            assert registro.temporada == TEMPORADA_SECA
            assert registro.es_fin_de_semana_o_feriado is True

    def test_un_conjunto_vacio_devuelve_lista_vacia_sin_excepcion(
        self, data_lake_canonico: DataLake
    ) -> None:
        assert data_lake_canonico.filtrar(dias_semana=set()) == []
        assert data_lake_canonico.filtrar(climas={"categoria_inexistente"}) == []
        assert data_lake_canonico.filtrar(temporadas={"otro_invierno"}) == []
        assert data_lake_canonico.filtrar(fecha=date(1999, 12, 31)) == []

    def test_una_combinacion_imposible_devuelve_lista_vacia(
        self, data_lake_canonico: DataLake
    ) -> None:
        """Una categoría climática ajena al vocabulario no puede tener coincidencias."""
        assert data_lake_canonico.filtrar(climas={"nieve_heladas"}) == []

    def test_una_combinacion_estrecha_sigue_coherente(
        self, data_lake_canonico: DataLake
    ) -> None:
        """Lunes de temporada de lluvias marcados como feriado, si los hay."""
        resultados = data_lake_canonico.filtrar(
            dias_semana={"lunes"},
            climas={"despejado"},
            temporadas={TEMPORADA_LLUVIAS},
            fin_de_semana_o_feriado=True,
        )
        for registro in resultados:
            assert registro.dia_semana == "lunes"
            assert registro.temporada == TEMPORADA_LLUVIAS
            assert registro.clima == "despejado"
            assert registro.es_fin_de_semana_o_feriado is True

    def test_el_data_lake_es_iterable_y_tiene_longitud(self, data_lake_canonico: DataLake) -> None:
        assert len(list(data_lake_canonico)) == len(data_lake_canonico) == 730
        assert len(data_lake_canonico.registros) == 730


class TestPromedioVisitantes:
    def test_devuelve_none_sin_registros(self) -> None:
        assert promedio_visitantes([]) is None

    def test_calcula_la_media(self, escribir_csv) -> None:
        data_lake = cargar_data_lake(escribir_csv("ok.csv", CSV_VALIDO))
        registros = data_lake.filtrar(temporadas={TEMPORADA_SECA})
        assert promedio_visitantes(registros) == (4500 + 5200 + 2000) / 3
