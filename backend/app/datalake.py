"""Calendario, esquema y consulta en memoria del Data Lake de Machu Picchu.

Este módulo es la única fuente de verdad del vocabulario del Data Lake (días de la
semana, temporadas, categorías climáticas, catálogo de feriados y capacidad máxima).
El generador de `datalake/generate_datalake.py` y la lógica de predicción de
`app/prediction.py` importan de aquí, de modo que el criterio con el que se marcan los
feriados sea literalmente el mismo en el CSV, en los tests y en la predicción.
"""

from __future__ import annotations

import csv
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DIAS_SEMANA: tuple[str, ...] = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

#: Días de lunes a viernes, sobre los que puede caer un feriado en día laborable.
DIAS_LABORABLES: frozenset[str] = frozenset(DIAS_SEMANA[:5])

NOMBRES_MES: tuple[str, ...] = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "setiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

TEMPORADA_SECA = "seca"
TEMPORADA_LLUVIAS = "lluvias"
TEMPORADAS: tuple[str, ...] = (TEMPORADA_SECA, TEMPORADA_LLUVIAS)

#: Meses de la temporada seca. De noviembre a abril corre la temporada de lluvias.
MESES_TEMPORADA_SECA: frozenset[int] = frozenset({5, 6, 7, 8, 9, 10})

CLIMA_DESPEJADO = "despejado"
CLIMA_NUBLADO = "nublado"
CLIMA_LLUVIA = "lluvia"
CLIMA_LLUVIA_TORRENCIAL = "lluvia_torrencial"
CLIMA_TORMENTA = "tormenta"
CLIMAS: tuple[str, ...] = (
    CLIMA_DESPEJADO,
    CLIMA_NUBLADO,
    CLIMA_LLUVIA,
    CLIMA_LLUVIA_TORRENCIAL,
    CLIMA_TORMENTA,
)

#: Categorías que reducen la afluencia respecto de la base de su temporada.
CLIMAS_MAL_TIEMPO: frozenset[str] = frozenset({CLIMA_LLUVIA_TORRENCIAL, CLIMA_TORMENTA})

#: Capacidad máxima oficial de visitantes por día.
CAPACIDAD_MAXIMA = 5600

COLUMNAS: tuple[str, ...] = (
    "fecha",
    "dia_semana",
    "temporada",
    "clima",
    "temperatura_c",
    "es_fin_de_semana_o_feriado",
    "visitantes_reales",
)

#: Ruta canónica del CSV, válida tanto en el árbol de fuentes como en la imagen Docker.
RUTA_POR_DEFECTO_DATALAKE: Path = (
    Path(__file__).resolve().parent.parent / "datalake" / "machupicchu_history.csv"
)

#: Comando que materializa el archivo cuando falta.
COMANDO_GENERADOR = "uv run python -m datalake.generate_datalake"


@dataclass(frozen=True, slots=True)
class Feriado:
    """Un feriado del catálogo fijo, identificado por mes y día."""

    nombre: str
    mes: int
    dia: int
    alcance: str


#: Catálogo fijo de feriados. Es un dato declarado en el código, no una consulta a una
#: API de días festivos: la generación del Data Lake debe ser determinista y funcionar
#: sin conexión. Incluye los feriados nacionales y el feriado regional de Cusco, que es
#: el que másluence tourism a Machu Picchu junto a las Fiestas Patrias.
FERIADOS_PERUANOS: tuple[Feriado, ...] = (
    Feriado("Año Nuevo", 1, 1, "nacional"),
    Feriado("Día de Reyes", 1, 6, "nacional"),
    Feriado("Día del Trabajo", 5, 1, "nacional"),
    Feriado("Inti Raymi", 6, 24, "cusco"),
    Feriado("San Pedro y San Pablo", 6, 29, "nacional"),
    Feriado("Fiesta de la Independencia", 7, 28, "nacional"),
    Feriado("Fiestas Patrias", 7, 29, "nacional"),
    Feriado("Combate de Angamos", 8, 6, "nacional"),
    Feriado("Inmaculada Concepción", 12, 8, "nacional"),
    Feriado("Navidad", 12, 25, "nacional"),
)


class DataLakeError(RuntimeError):
    """El Data Lake no se pudo cargar: falta el archivo o su esquema no coincide."""


def nombre_dia_semana(fecha: date) -> str:
    """Devuelve el nombre del día de la semana en español."""
    return DIAS_SEMANA[fecha.weekday()]


def nombre_mes(fecha: date) -> str:
    """Devuelve el nombre del mes en español."""
    return NOMBRES_MES[fecha.month - 1]


def fecha_en_espanol(fecha: date) -> str:
    """Devuelve la fecha escrita en español, por ejemplo `24 de junio de 2026`."""
    return f"{fecha.day} de {nombre_mes(fecha)} de {fecha.year}"


def temporada_de(fecha: date) -> str:
    """Devuelve `seca` para mayo-octubre y `lluvias` para noviembre-abril."""
    return TEMPORADA_SECA if fecha.month in MESES_TEMPORADA_SECA else TEMPORADA_LLUVIAS


def feriado_de(fecha: date) -> Feriado | None:
    """Devuelve el feriado del catálogo que cae en esa fecha, o `None`."""
    for feriado in FERIADOS_PERUANOS:
        if feriado.mes == fecha.month and feriado.dia == fecha.day:
            return feriado
    return None


def es_feriado(fecha: date) -> bool:
    """Indica si la fecha es un feriado del catálogo."""
    return feriado_de(fecha) is not None


def es_fin_de_semana_o_feriado(fecha: date) -> bool:
    """Indica sábado, domingo o feriado del catálogo.

    Este es el criterio único con el que el Data Lake marca su columna
    `es_fin_de_semana_o_feriado` y con el que la predicción clasifica la fecha
    objetivo, de modo que un feriado que cae de lunes a viernes se agrupa con los fines
    de semana.
    """
    return fecha.weekday() >= 5 or es_feriado(fecha)


def texto_booleano(valor: bool) -> str:
    """Serializa un booleano con la convención del CSV (`true`/`false`)."""
    return "true" if valor else "false"


def es_buen_tiempo(clima: str) -> bool:
    """Indica si el clima no reduce la afluencia."""
    return clima not in CLIMAS_MAL_TIEMPO


@dataclass(frozen=True, slots=True)
class Registro:
    """Un día del historial de visitantes de Machu Picchu."""

    fecha: date
    dia_semana: str
    temporada: str
    clima: str
    temperatura_c: float
    es_fin_de_semana_o_feriado: bool
    visitantes_reales: int


def _parsear_fecha(valor: str, ruta: Path, numero_linea: int) -> date:
    try:
        return date.fromisoformat(valor.strip())
    except ValueError as exc:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} tiene una fecha inválida {valor!r}; "
            "se espera el formato YYYY-MM-DD"
        ) from exc


def registro_desde_fila(fila: dict[str, str | None], ruta: Path, numero_linea: int) -> Registro:
    """Construye un `Registro` validando los valores de una fila del CSV.

    `csv.DictReader` rellena con `None` las columnas que faltan en una fila corta y deja
    las sobrantes bajo la clave `None`, así que aquí se comprueba la forma antes de leer
    los valores. Sin esa comprobación, una fila truncada escaparía como `AttributeError`
    y una fila con una columna de más se aceptaría en silencio.
    """
    sobrantes = fila.get(None)
    if sobrantes:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} tiene {len(sobrantes)} columna(s) de más: "
            f"{', '.join(sobrantes)}"
        )
    ausentes = [columna for columna in COLUMNAS if fila.get(columna) is None]
    if ausentes:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} está truncada, le faltan las columnas "
            f"{', '.join(ausentes)}"
        )

    assert isinstance(fila["clima"], str)  # Narrowing para el analizador estático.
    assert isinstance(fila["temporada"], str)
    assert isinstance(fila["dia_semana"], str)
    assert isinstance(fila["es_fin_de_semana_o_feriado"], str)
    try:
        clima = fila["clima"].strip()
        temporada = fila["temporada"].strip()
        dia_semana = fila["dia_semana"].strip()
        temperatura = float(fila["temperatura_c"])
        visitantes = int(fila["visitantes_reales"])
        marca = fila["es_fin_de_semana_o_feriado"].strip().lower()
    except (TypeError, ValueError) as exc:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} tiene un valor no numérico: {exc}"
        ) from exc

    if clima not in CLIMAS:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} declara el clima {clima!r}, que no está en "
            f"el vocabulario {', '.join(CLIMAS)}"
        )
    if temporada not in TEMPORADAS:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} declara la temporada {temporada!r}, que no "
            f"está en el vocabulario {', '.join(TEMPORADAS)}"
        )
    if dia_semana not in DIAS_SEMANA:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} declara el día de la semana {dia_semana!r}, "
            f"que no está en el vocabulario {', '.join(DIAS_SEMANA)}"
        )
    if marca not in {"true", "false"}:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} declara "
            f"es_fin_de_semana_o_feriado={marca!r}, que no es un booleano"
        )
    if visitantes < 0:
        raise DataLakeError(
            f"{ruta}: la fila {numero_linea} declara un número de visitantes negativo"
        )

    return Registro(
        fecha=_parsear_fecha(fila["fecha"], ruta, numero_linea),
        dia_semana=dia_semana,
        temporada=temporada,
        clima=clima,
        temperatura_c=temperatura,
        es_fin_de_semana_o_feriado=marca == "true",
        visitantes_reales=visitantes,
    )


def promedio_visitantes(registros: Sequence[Registro]) -> float | None:
    """Devuelve la media de visitantes, o `None` si no hay registros."""
    if not registros:
        return None
    return sum(r.visitantes_reales for r in registros) / len(registros)


class DataLake:
    """Historial de visitantes cargado en memoria y consultable por filtros."""

    def __init__(self, registros: Iterable[Registro], ruta: Path) -> None:
        self._registros: tuple[Registro, ...] = tuple(registros)
        self.ruta = ruta

    def __len__(self) -> int:
        return len(self._registros)

    def __iter__(self):
        return iter(self._registros)

    @property
    def registros(self) -> tuple[Registro, ...]:
        return self._registros

    @property
    def rango_fechas(self) -> tuple[date, date]:
        """Primera y última fecha del historial."""
        fechas = [registro.fecha for registro in self._registros]
        return min(fechas), max(fechas)

    def por_fecha(self, fecha: date) -> list[Registro]:
        """Devuelve el registro de una fecha concreta, o una lista vacía."""
        return [registro for registro in self._registros if registro.fecha == fecha]

    def filtrar(
        self,
        *,
        dias_semana: Collection[str] | None = None,
        climas: Collection[str] | None = None,
        temporadas: Collection[str] | None = None,
        fin_de_semana_o_feriado: bool | None = None,
        fecha: date | None = None,
    ) -> list[Registro]:
        """Devuelve los registros que cumplen todos los filtros indicados.

        Un filtro sin coincidencias devuelve una lista vacía; ningún filtro lanza
        excepción por no encontrar resultados.
        """
        resultado = self._registros
        if dias_semana is not None:
            wanted = set(dias_semana)
            resultado = [r for r in resultado if r.dia_semana in wanted]
        if climas is not None:
            wanted = set(climas)
            resultado = [r for r in resultado if r.clima in wanted]
        if temporadas is not None:
            wanted = set(temporadas)
            resultado = [r for r in resultado if r.temporada in wanted]
        if fin_de_semana_o_feriado is not None:
            resultado = [
                r
                for r in resultado
                if r.es_fin_de_semana_o_feriado is fin_de_semana_o_feriado
            ]
        if fecha is not None:
            resultado = [r for r in resultado if r.fecha == fecha]
        return list(resultado)


def validar_encabezados(encabezados: Sequence[str], ruta: Path) -> None:
    """Comprueba que el encabezado del CSV coincide con el esquema esperado."""
    if list(encabezados) == list(COLUMNAS):
        return

    faltantes = [columna for columna in COLUMNAS if columna not in encabezados]
    sobrantes = [columna for columna in encabezados if columna not in COLUMNAS]

    detalles: list[str] = []
    if faltantes:
        detalles.append(f"faltan las columnas {', '.join(faltantes)}")
    if sobrantes:
        detalles.append(f"sobran las columnas {', '.join(sobrantes)}")
    if not detalles:
        detalles.append(
            f"el orden de las columnas es {', '.join(encabezados)}, y se espera "
            f"{', '.join(COLUMNAS)}"
        )

    raise DataLakeError(
        f"{ruta}: el encabezado del Data Lake no coincide con el esquema. "
        f"{'; '.join(detalles)}."
    )


def cargar_data_lake(ruta: Path | str | None = None) -> DataLake:
    """Lee el CSV del Data Lake una sola vez y lo devuelve en memoria."""
    ruta_csv = Path(ruta) if ruta is not None else RUTA_POR_DEFECTO_DATALAKE

    if not ruta_csv.is_file():
        raise DataLakeError(
            f"No se encontró el Data Lake en {ruta_csv}. Genéralo con: {COMANDO_GENERADOR}"
        )

    with ruta_csv.open(encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)
        encabezados = lector.fieldnames or []
        validar_encabezados(encabezados, ruta_csv)
        registros = [
            registro_desde_fila(fila, ruta_csv, numero_linea)
            for numero_linea, fila in enumerate(lector, start=2)
        ]

    if not registros:
        raise DataLakeError(
            f"{ruta_csv}: el Data Lake no tiene filas de datos, sólo el encabezado."
        )

    return DataLake(registros, ruta_csv)
