# Proposal

## Why

Machu Picchu tiene un aforo oficial diario limitado (5,600 visitantes) y la demanda
varía fortement según el clima, la temporada y el día de la semana, pero no existe
ninguna herramienta en este repositorio que traduzca esa demanda en un número
accionable antes de que el turista viaje. Este cambio construye desde cero el sistema
completo de predicción: un Data Lake sintético en CSV con 2 años de historial, un
backend que lo cruza con el pronóstico real de Open-Meteo, y un frontend web
minimalista para consultar la previsión del día de hoy o de cualquier fecha elegida.

Es el cambio fundacional del proyecto: el repositorio sólo contiene el contrato
(`openspec/project.md`) y no tiene código, por lo que este change establece tanto la
implementación como las capacidades que la verificación posterior controlará mediante
specs.

## What Changes

- **Data Lake sintético en CSV**: script generador (`backend/datalake/`) que produce
  `machupicchu_history.csv` con 730 días de registros deterministas (rango de fechas
  con época fija + semilla fija) que aplica las reglas de negocio de temporada,
  clima, fin de semana/feriado y capacidad máxima de 5,600 visitantes/día.
- **Servicio backend FastAPI** con `uv`, `httpx` y `pydantic-settings`:
  - Cliente de Open-Meteo para las coordenadas de Machu Picchu
    (`latitude=-13.1631`, `longitude=-72.5450`) con mapeo de `weathercode` a
    condición en español.
  - Motor de predicción que cruza el pronóstico con los registros similares del
    CSV y estima visitantes, porcentaje de aforo y nivel de afluencia
    (Bajo < 3,000 / Moderado 3,000–4,500 / Alto > 4,500).
  - `GET /api/prediction?date=YYYY-MM-DD` con validación de la ventana de pronóstico
    y `GET /health`.
- **Frontend Angular 20** standalone (signals, sin SSR, CSS puro) con input nativo
  de fecha que por defecto muestra hoy, botón "Consultar Afluencia" y tarjeta de
  resultado con clima, visitantes estimados, barra de aforo y etiqueta de nivel.
- **Infraestructura**: `backend/Dockerfile` sobre `python:3.12-slim`,
  `frontend/Dockerfile` multi-stage (`node:20-alpine` → `nginx:1.27-alpine`) con proxy
  de `/api/*`, e `infra/docker-compose.yml` con ambos servicios (memoria runtime
  < 400 MB).
- **Testing**: pytest con `respx` para mockear Open-Meteo y umbral de cobertura
  `--cov-fail-under=80`.

### Decisiones de alcance tomadas en el proposal

- **Ventana de pronóstico acotada**: `GET /api/prediction` sólo acepta fechas dentro
  de la ventana del endpoint de pronóstico de Open-Meteo (hoy .. hoy+N días). Las
  fechas fuera de rango devuelven `422` con un mensaje explícito que indica el rango
  soportado. No se inventa clima ni se cae a climatología del CSV, y no se integra la
  API de archivo histórico de Open-Meteo.
- **CSV determinista**: el rango de fechas del Data Lake parte de una época fija
  codificada en el generador y usa una semilla aleatoria fija, de modo que el archivo
  es byte-idéntico en cada ejecución. Esto hace reproducibles tanto las predicciones
  como los tests.
- **Artefactos en español**: los specs y el código siguen el idioma del contrato
  `openspec/project.md`.

## Capabilities

### New Capabilities

- `data-lake`: Generación del CSV sintético de 730 días (determinista, con las
  columnas y reglas de negocio definidas) y su lectura/consulta en memoria por
  fecha, día de la semana y temporada.
- `visitor-prediction`: Lógica de predicción de visitantes y capacidad, cliente de
  Open-Meteo, y los endpoints HTTP `GET /api/prediction` y `GET /health`.
- `prediction-web-ui`: SPA Angular 20 con selector de fecha, acción de consulta y
  tarjeta de resultado (clima, visitantes estimados, aforo, nivel de afluencia).
- `containerized-deployment`: Imágenes Docker de backend y frontend, proxy inverso
  Nginx de `/api/*` y composición con `docker compose` de los dos servicios.

### Modified Capabilities

Ninguna. `openspec/specs/` está vacío; todas las capacidades son nuevas.

## Impact

- **Código nuevo**: `backend/` (paquete Python, generador del Data Lake, tests
  pytest), `frontend/` (proyecto Angular 20), `infra/docker-compose.yml`.
- **APIs**: dos endpoints REST nuevos, sin clientes previos ni contratos que romper.
- **Dependencias**: Python 3.12 (FastAPI, uvicorn, httpx, pydantic, pytest, respx,
  pytest-cov), Node 20 + Angular 20 CLI para el build del frontend; Docker y
  `docker compose` v2 para el despliegue.
- **Datos**: se añade `backend/datalake/machupicchu_history.csv` (~730 filas,
  sintético, sin datos personales ni copyrighted de terceros) generado por código.
- **Sistemas**: consume Open-Meteo (API pública sin clave) en cada consulta de
  predicción; requiere salida a Internet desde el contenedor backend.
- **Restricciones**: memoria total de runtime < 400 MB (orientado a EC2 t3.micro).
