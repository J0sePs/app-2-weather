"""Contrato del generador del Data Lake: determinismo, opciones y encabezado.

El generador es código de preparación de datos y queda fuera de la cobertura de `app`
(ver `design.md`, decisión 11), pero sí tiene su propia suite: si dejara de ser
determinista, el CSV versionado y los tests que lo leen dejarían de ser reproducibles.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from datalake.generate_datalake import (
    DIAS_HISTORIAL,
    FECHA_INICIO,
    RANGO_BASE,
    SEMILLA,
    calcular_visitantes,
    elegir_clima,
    generar,
    generar_registros,
)
from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMAS,
    COLUMNAS,
    RUTA_POR_DEFECTO_DATALAKE,
    TEMPORADA_LLUVIAS,
    TEMPORADA_SECA,
    es_buen_tiempo,
)


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


class TestDeterminismo:
    def test_dos_generaciones_en_el_mismo_proceso_coinciden(self) -> None:
        primera = generar_registros()
        segunda = generar_registros()
        assert primera == segunda

    def test_dos_ejecuciones_separadas_son_identicas_byte_a_byte(self, tmp_path: Path) -> None:
        uno = tmp_path / "uno.csv"
        dos = tmp_path / "dos.csv"
        generar(salida=uno)
        generar(salida=dos)
        assert _hash(uno) == _hash(dos)
        assert uno.read_bytes() == dos.read_bytes()

    def test_el_csv_canonico_versionado_coincide_con_una_generacion_nueva(
        self, tmp_path: Path, ruta_csv_canonico: Path
    ) -> None:
        """El CSV del repositorio está al día respecto del generador."""
        regenerado = tmp_path / "regenerado.csv"
        generar(salida=regenerado)
        assert _hash(regenerado) == _hash(ruta_csv_canonico)

    def test_cambiar_la_semilla_cambia_el_contenido(self) -> None:
        original = generar_registros(semilla=SEMILLA)
        distinto = generar_registros(semilla=SEMILLA + 1)
        assert original != distinto

    def test_el_rango_por_defecto_esta_fijado_en_el_codigo(self) -> None:
        assert FECHA_INICIO == date(2025, 1, 1)
        assert DIAS_HISTORIAL == 730


class TestOpcionesDelGenerador:
    def test_sin_argumentos_escribe_en_el_archivo_canonico(self) -> None:
        ruta = generar()
        assert ruta == RUTA_POR_DEFECTO_DATALAKE
        assert ruta.is_file()
        assert len(ruta.read_text(encoding="utf-8").splitlines()) == DIAS_HISTORIAL + 1

    def test_el_rango_personalizable_arranca_en_la_fecha_pedida(self, tmp_path: Path) -> None:
        ruta = generar(salida=tmp_path / "p.csv", fecha_inicio=date(2024, 3, 1))
        filas = ruta.read_text(encoding="utf-8").splitlines()
        assert filas[0] == ",".join(COLUMNAS)
        assert filas[1].startswith("2024-03-01,")
        assert len(filas) == DIAS_HISTORIAL + 1

    def test_el_rango_personalizable_cubre_730_dias_consecutivos(self, tmp_path: Path) -> None:
        inicio = date(2024, 3, 1)
        ruta = generar(salida=tmp_path / "p.csv", fecha_inicio=inicio)
        fechas = [
            date.fromisoformat(linea.split(",")[0])
            for linea in ruta.read_text(encoding="utf-8").splitlines()[1:]
        ]
        assert fechas[0] == inicio
        assert (fechas[-1] - inicio).days == DIAS_HISTORIAL - 1
        assert len(set(fechas)) == DIAS_HISTORIAL

    def test_el_parser_acepta_salida_y_fecha_inicio(self, tmp_path: Path) -> None:
        from datalake.generate_datalake import main

        ruta = tmp_path / "cli.csv"
        codigo = main(["--salida", str(ruta), "--fecha-inicio", "2024-01-15"])
        assert codigo == 0
        assert ruta.read_text(encoding="utf-8").splitlines()[1].startswith("2024-01-15,")

    def test_el_parser_por_defecto_usa_la_epoca_fija(self) -> None:
        from datalake.generate_datalake import construir_parser

        argumentos = construir_parser().parse_args([])
        assert argumentos.fecha_inicio == FECHA_INICIO
        assert argumentos.salida is None


class TestEstructuraDeLasFilas:
    def test_cada_fila_tiene_las_columnas_del_esquema(self) -> None:
        for fila in generar_registros()[:20]:
            assert tuple(fila) == COLUMNAS

    def test_las_fechas_son_consecutivas_desde_la_epoca(self) -> None:
        filas = generar_registros()
        fechas = [date.fromisoformat(fila["fecha"]) for fila in filas]
        assert fechas[0] == FECHA_INICIO
        for anterior, siguiente in zip(fechas, fechas[1:], strict=False):
            assert (siguiente - anterior).days == 1

    def test_las_visitas_son_enteros_dentro_del_aforo(self) -> None:
        for fila in generar_registros():
            visitantes = int(fila["visitantes_reales"])
            assert 0 <= visitantes <= CAPACIDAD_MAXIMA

    def test_la_temperatura_tiene_un_decimal(self) -> None:
        for fila in generar_registros()[:20]:
            assert fila["temperatura_c"].count(".") == 1

    def test_la_marca_booleana_usa_true_y_false(self) -> None:
        marcas = {fila["es_fin_de_semana_o_feriado"] for fila in generar_registros()}
        assert marcas == {"true", "false"}


class TestReglasDeCalculo:
    def test_la_base_se_sortea_dentro_del_rango_de_la_temporada(self) -> None:
        import random

        aleatorio = random.Random(SEMILLA)
        for _ in range(200):
            minimo, maximo = RANGO_BASE[TEMPORADA_SECA]
            valor = calcular_visitantes(aleatorio, TEMPORADA_SECA, "despejado", False)
            assert minimo <= valor <= maximo

    def test_el_fin_de_semana_aumenta_un_15_por_ciento(self) -> None:
        import random

        base_valor = RANGO_BASE[TEMPORADA_SECA][0]
        sin_finde = calcular_visitantes(
            random.Random(1), TEMPORADA_SECA, "despejado", False
        )
        con_finde = calcular_visitantes(
            random.Random(1), TEMPORADA_SECA, "despejado", True
        )
        assert con_finde == min(CAPACIDAD_MAXIMA, round(sin_finde * 1.15))
        assert base_valor > 0

    def test_el_mal_tiempo_reduce_la_afluencia(self) -> None:
        import random

        for clima_mal in ("lluvia_torrencial", "tormenta"):
            sin_mal = calcular_visitantes(random.Random(7), TEMPORADA_SECA, "despejado", False)
            con_mal = calcular_visitantes(random.Random(7), TEMPORADA_SECA, clima_mal, False)
            assert con_mal < sin_mal

    def test_el_resultado_se_acota_a_la_capacidad_maxima(self) -> None:
        import random

        # Una base de temporada seca multiplicada por 1,15 superaría el aforo oficial.
        for semilla in range(500):
            valor = calcular_visitantes(
                random.Random(semilla), TEMPORADA_SECA, "despejado", True
            )
            assert valor <= CAPACIDAD_MAXIMA
            assert valor >= 0

    def test_las_temporadas_tienen_distintas_distribuciones_de_clima(self) -> None:
        import random

        def frecuencia(temporada: str) -> dict[str, int]:
            aleatorio = random.Random(SEMILLA)
            conteo = {clima: 0 for clima in CLIMAS}
            for _ in range(4000):
                conteo[elegir_clima(aleatorio, temporada)] += 1
            return conteo

        seca = frecuencia(TEMPORADA_SECA)
        lluvias = frecuencia(TEMPORADA_LLUVIAS)
        assert seca["despejado"] > lluvias["despejado"]
        assert (
            seca["lluvia_torrencial"] + seca["tormenta"]
            < lluvias["lluvia_torrencial"] + lluvias["tormenta"]
        )

    def test_el_clima_generado_esta_en_el_vocabulario(self) -> None:
        for fila in generar_registros():
            assert fila["clima"] in CLIMAS
            assert (fila["clima"] in {"lluvia_torrencial", "tormenta"}) == (
                not es_buen_tiempo(fila["clima"])
            )


class TestSalidaEnDisco:
    def test_el_archivo_generado_se_puede_volver_a_cargar(self, tmp_path: Path) -> None:
        from app.datalake import cargar_data_lake

        ruta = generar(salida=tmp_path / "cargable.csv")
        data_lake = cargar_data_lake(ruta)
        assert len(data_lake) == DIAS_HISTORIAL
        assert data_lake.ruta == ruta

    def test_el_archivo_se_escribe_sin_saltos_de_linea_crlf(self, tmp_path: Path) -> None:
        ruta = generar(salida=tmp_path / "unix.csv")
        assert b"\r\n" not in ruta.read_bytes()

    def test_el_directorio_de_salida_se_crea_si_no_existe(self, tmp_path: Path) -> None:
        destino = tmp_path / "nuevo" / "datalake.csv"
        generar(salida=destino)
        assert destino.is_file()

    def test_la_temporada_registrada_corresponde_al_mes(self) -> None:
        for fila in generar_registros():
            mes = date.fromisoformat(fila["fecha"]).month
            esperada = TEMPORADA_SECA if mes in {5, 6, 7, 8, 9, 10} else TEMPORADA_LLUVIAS
            assert fila["temporada"] == esperada

    def test_la_temporada_de_lluvias_aparece_en_el_csv(self) -> None:
        assert {fila["temporada"] for fila in generar_registros()} == {
            TEMPORADA_SECA,
            TEMPORADA_LLUVIAS,
        }
