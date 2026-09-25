# Imagen del backend: Python 3.12 slim, dependencias con uv, usuario sin privilegios.
#
# El Data Lake se copia a la misma ruta que el backend espera por omisión
# (`/app/datalake/machupicchu_history.csv`), de modo que la imagen arranca sin
# variables de entorno. Montar otro CSV es cuestión de `MP_RUTA_DATALAKE`.

# syntax=docker/dockerfile:1

# ---------- etapa de dependencias ----------
FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.12 /uv /usr/local/bin/uv

# Se copia primero sólo el manifiesto para que la instalación de dependencias se
# aproveche en caché mientras el código cambie.
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# ---------- imagen final ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=America/Lima \
    MP_RUTA_DATALAKE=/app/datalake/machupicchu_history.csv \
    MP_LOG_LEVEL=INFO

# `tzdata` es obligatorio: la fecha de hoy se calcula en `America/Lima`, y una
# imagen slim sin base de datos de zonas devolvería la fecha en UTC.
RUN apt-get update \
    && apt-get install --no-install-recommends -y tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

# El paquete `app` y el generador del Data Lake.
COPY app ./app
COPY datalake ./datalake

# Usuario sin privilegios: el proceso del servidor no corre como root.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin machupicchu \
    && chown -R machupicchu:machupicchu /app
USER machupicchu

EXPOSE 8000

# Un solo worker: el despliegue es pequeño y el Data Lake se carga una vez por proceso.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
