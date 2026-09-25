"""Generador del Data Lake sintético de Machu Picchu.

Produce `datalake/machupicchu_history.csv` con 730 días consecutivos de historial
sintético. La generación es determinista: la fecha de inicio y la semilla aleatoria
están fijadas en el código, así que dos ejecuciones con la misma configuración producen
un archivo idéntico byte a byte.

Uso:

    uv run python -m datalake.generate_datalake
    uv run python -m datalake.generate_datalake --salida /tmp/h.csv --fecha-inicio 2024-01-01
"""

from __future__ import annotations

import argparse
import csv
import random
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from app.datalake import (
    CAPACIDAD_MAXIMA,
    CLIMA_DESPEJADO,
    CLIMA_LLUVIA,
    CLIMA_LLUVIA_TORRENCIAL,
    CLIMA_NUBLADO,
    CLIMA_TORMENTA,
    COLUMNAS,
    TEMPORADA_LLUVIAS,
    TEMPORADA_SECA,
    es_buen_tiempo,
    es_fin_de_semana_o_feriado,
    nombre_dia_semana,
    temporada_de,
    texto_booleano,
)

#: Época fija de inicio del historial. No es la fecha de ejecución: el conjunto de
#: datos no debe cambiar según el día en que se regenere.
FECHA_INICIO: date = date(2025, 1, 1)

#: Semilla fija de la dispersión aleatoria.
SEMILLA: int = 20260926

#: Número de días consecutivos del historial.
DIAS_HISTORIAL = 730

#: Rango de afluencia base por temporada, para días laborables de buen tiempo.
RANGO_BASE: dict[str, tuple[int, int]] = {
    TEMPORADA_SECA: (4000, 5200),
    TEMPORADA_LLUVIAS: (1800, 3200),
}

#: Rango de temperatura en décimas de grado, por temporada.
RANGO_TEMPERATURA: dict[str, tuple[int, int]] = {
    TEMPORADA_SECA: (140, 265),
    TEMPORADA_LLUVIAS: (85, 225),
}

#: Multiplicador de fin de semana y feriado sobre la base.
MULTIPLICADOR_FIN_DE_SEMANA = 1.15

#: Multiplicador del mal tiempo (lluvia torrencial o tormenta) sobre la base.
MULTIPLICADOR_MAL_TIEMPO = 0.55

#: Distribución del clima por temporada, como (categoría, peso) y en el orden de
#: `CLIMAS` para que la suma de los pesos sea legible junto a la tabla.
PESOS_CLIMA: dict[str, tuple[tuple[str, float], ...]] = {
    TEMPORADA_SECA: (
        (CLIMA_DESPEJADO, 0.42),
        (CLIMA_NUBLADO, 0.28),
        (CLIMA_LLUVIA, 0.20),
        (CLIMA_LLUVIA_TORRENCIAL, 0.07),
        (CLIMA_TORMENTA, 0.03),
    ),
    TEMPORADA_LLUVIAS: (
        (CLIMA_DESPEJADO, 0.10),
        (CLIMA_NUBLADO, 0.24),
        (CLIMA_LLUVIA, 0.30),
        (CLIMA_LLUVIA_TORRENCIAL, 0.21),
        (CLIMA_TORMENTA, 0.15),
    ),
}


def elegir_clima(aleatorio: random.Random, temporada: str) -> str:
    """Sortea una categoría climática según la distribución de la temporada."""
    pesos = PESOS_CLIMA[temporada]
    return aleatorio.choices(
        [categoria for categoria, _ in pesos],
        weights=[peso for _, peso in pesos],
        k=1,
    )[0]


def calcular_visitantes(
    aleatorio: random.Random,
    temporada: str,
    clima: str,
    es_finde: bool,
) -> int:
    """Calcula `visitantes_reales` aplicando las reglas de negocio del sitio.

    La base se sortea dentro del rango de la temporada, el fin de semana o feriado la
    multiplica por 1,15, el mal tiempo la reduce a la mitad y el resultado se acota a
    la capacidad máxima oficial.
    """
    minimo, maximo = RANGO_BASE[temporada]
    visitantes = float(aleatorio.randint(minimo, maximo))

    if es_finde:
        visitantes *= MULTIPLICADOR_FIN_DE_SEMANA
    if not es_buen_tiempo(clima):
        visitantes *= MULTIPLICADOR_MAL_TIEMPO

    acotado = min(CAPACIDAD_MAXIMA, max(0, round(visitantes)))
    return acotado


def generar_registros(
    fecha_inicio: date = FECHA_INICIO,
    dias: int = DIAS_HISTORIAL,
    semilla: int = SEMILLA,
) -> list[dict[str, str]]:
    """Genera las filas del Data Lake en orden cronológico."""
    aleatorio = random.Random(semilla)
    filas: list[dict[str, str]] = []

    for indice in range(dias):
        fecha = fecha_inicio + timedelta(days=indice)
        temporada = temporada_de(fecha)
        clima = elegir_clima(aleatorio, temporada)
        es_finde = es_fin_de_semana_o_feriado(fecha)
        min_temp, max_temp = RANGO_TEMPERATURA[temporada]
        temperatura = aleatorio.randint(min_temp, max_temp) / 10

        filas.append(
            {
                "fecha": fecha.isoformat(),
                "dia_semana": nombre_dia_semana(fecha),
                "temporada": temporada,
                "clima": clima,
                "temperatura_c": f"{temperatura:.1f}",
                "es_fin_de_semana_o_feriado": texto_booleano(es_finde),
                "visitantes_reales": str(
                    calcular_visitantes(aleatorio, temporada, clima, es_finde)
                ),
            }
        )

    return filas


def escribir_csv(filas: Sequence[dict[str, str]], salida: Path) -> Path:
    """Escribe las filas en `salida` con encabezado y fin de línea `\\n`."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(
            archivo, fieldnames=list(COLUMNAS), lineterminator="\n"
        )
        escritor.writeheader()
        escritor.writerows(filas)
    return salida


def generar(
    salida: Path | str | None = None,
    fecha_inicio: date = FECHA_INICIO,
) -> Path:
    """Genera el Data Lake y devuelve la ruta del archivo escrito."""
    ruta = Path(salida) if salida is not None else Path(__file__).resolve().parent / "machupicchu_history.csv"
    filas = generar_registros(fecha_inicio=fecha_inicio)
    return escribir_csv(filas, ruta)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m datalake.generate_datalake",
        description=(
            "Genera el Data Lake sintético de Machu Picchu. Es determinista: la misma "
            "configuración produce siempre un archivo idéntico."
        ),
    )
    parser.add_argument(
        "--salida",
        "-o",
        type=Path,
        default=None,
        help="ruta del CSV de salida (por defecto backend/datalake/machupicchu_history.csv)",
    )
    parser.add_argument(
        "--fecha-inicio",
        type=date.fromisoformat,
        default=FECHA_INICIO,
        help=f"primera fecha del historial en YYYY-MM-DD (por defecto {FECHA_INICIO.isoformat()})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    ruta = generar(salida=argumentos.salida, fecha_inicio=argumentos.fecha_inicio)
    print(f"Data Lake generado en {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
