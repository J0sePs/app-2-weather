# Predicción de Afluencia - Machu Picchu

Backend FastAPI del predictor de afluencia de Machu Picchu. Consulta el pronóstico
de Open-Meteo y lo cruza con el Data Lake sintético para estimar visitantes.

## Desarrollo

```bash
uv sync                                    # resuelve el entorno
uv run python -m datalake.generate_datalake  # genera el CSV canónico
uv run uvicorn app.main:app --reload        # sirve en http://127.0.0.1:8000
```

## Tests

```bash
uv run pytest
uv run pytest --cov=app --cov-report=term-missing
```

## API

- `GET /api/prediction?date=YYYY-MM-DD` — predicción de afluencia.
- `GET /health` — sonda de salud, sin dependencias externas.
- `GET /docs` — documentación interactiva.
