# Machu Picchu Visitor Predictor & Data Lake

## Purpose
Aplicación web minimalista para predecir la afluencia de turistas a Machu Picchu (Cuzco) para el día de hoy o cualquier fecha seleccionada por el usuario. Cruza el pronóstico meteorológico obtenido de Open-Meteo con un Data Lake sintético en CSV de 2 años de historial para estimar la cantidad de visitantes y el porcentaje de aforo.

## Tech Stack

### Backend
- **Language:** Python 3.12
- **Framework:** FastAPI 0.115+
- **ASGI server:** uvicorn 0.32+
- **Package manager:** uv (usar pyproject.toml)
- **HTTP client:** httpx 0.28+ (para consumir Open-Meteo)
- **Validation:** pydantic 2.10+ y pydantic-settings
- **Data Lake Engine:** Lector nativo en Python de archivos CSV locales

### Frontend
- **Framework:** Angular 20 (standalone components + signals)
- **Package manager:** npm
- **SSR:** desactivado (SPA pura)
- **Estilos:** CSS puro responsivo
- **HTTP:** HttpClient
- **UI Controls:** Input de fecha nativo (`<input type="date">`) con valor por defecto en la fecha actual

### External APIs
- **Open-Meteo API** (gratis, sin API key):
  - Coordenadas de Machu Picchu: `latitude=-13.1631&longitude=-72.5450`
  - Endpoint de pronóstico diario: `https://api.open-meteo.com/v1/forecast?latitude=-13.1631&longitude=-72.5450&daily=temperature_2m_max,precipitation_probability_max,weathercode&timezone=auto`

### Data Lake (CSV)
- **Archivo:** `backend/datalake/machupicchu_history.csv`
- **Registros:** 730 días sintéticos (2 años) con columnas:
  `fecha,dia_semana,temporada,clima,temperatura_c,es_fin_de_semana_o_feriado,visitantes_reales`
- **Reglas del negocio:**
  - Capacidad máxima oficial: 5,600 personas/día.
  - Temporada seca (mayo-octubre): alta afluencia base (~4,000 - 5,200).
  - Temporada de lluvias (noviembre-abril): afluencia baja (~1,800 - 3,200).
  - Lluvia torrencial o tormenta: reduce visitas.
  - Fin de semana y feriado: aumenta afluencia (+15%).

### Prediction Logic
- Entrada: Fecha seleccionada (`target_date`) en formato YYYY-MM-DD (por defecto hoy).
- Proceso:
  1. Obtiene el clima pronosticado para esa fecha en Machu Picchu.
  2. Identifica si la fecha es fin de semana y su temporada (mes).
  3. Filtra registros similares en el CSV del Data Lake y promedia los visitantes.
  4. Calcula el nivel de afluencia:
     - "Bajo" (< 3,000 personas)
     - "Moderado" (3,000 a 4,500 personas)
     - "Alto" (> 4,500 personas)

## API Endpoints
- `GET /api/prediction?date=YYYY-MM-DD` → Devuelve:
  ```json
  {
    "site": "Machu Picchu",
    "target_date": "2026-09-26",
    "weather": {
      "temperature_max": 24.5,
      "precipitation_probability": 15,
      "condition": "Nublado"
    },
    "prediction": {
      "estimated_visitors": 4580,
      "capacity_percentage": 81.8,
      "crowd_level": "Alto"
    }
  }
  ```
- `GET /health` → Devuelve `{"status": "ok"}`

## Frontend UI
- Encabezado: "Predicción de Afluencia - Machu Picchu".
- Barra de control:
  - Input selector de fecha con icono de calendario (`<input type="date">`).
  - Botón "Consultar Afluencia".
- Tarjeta de resultado (`PredictionCard`):
  - Clima esperado: Temperatura y condición atmosférica.
  - Visitantes estimados: `~4,580 personas`.
  - Barra de capacidad o porcentaje: `82% del aforo permitido`.
  - Etiqueta de nivel: `Afluencia Alta`.

## Testing & Quality
- Pytest en backend con umbral mínimo de 80% (`--cov-fail-under=80`).
- Mocking de llamadas a Open-Meteo usando `respx`.

## Infrastructure & Constraints
- Docker Compose v2 con 2 servicios:
  - `backend`: `python:3.12-slim` en puerto interno 8000.
  - `frontend`: Multi-stage (`node:20-alpine` -> `nginx:1.27-alpine`), expone solo puerto 80 y hace proxy de `/api/*` al backend.
- Memoria total en runtime < 400 MB (orientado a EC2 t3.micro con 1 GB RAM).
