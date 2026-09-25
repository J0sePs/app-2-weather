# Predicción de Afluencia - Machu Picchu

Estima cuántos visitantes se esperan en Machu Picchu a partir del pronóstico del clima
de Open-Meteo y de un historial sintético de dos años. Sin cuentas, sin claves de API
y sin servicios de pago.

La estimación **no es un dato oficial**: el historial es sintético y la tarjeta de
resultado lo advierte siempre en pantalla.

## Despliegue

Sólo hace falta Docker. Desde el clon:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Y abrir <http://localhost>. La UI y la API se sirven desde el mismo origen: Nginx
sirve la aplicación y hace de proxy inverso de `/api/` hacia el backend, de modo que
el navegador no necesita CORS.

Para comprobar que responde:

```bash
docker compose -f infra/docker-compose.yml ps                       # ambos servicios "healthy"
curl "http://localhost/api/prediction?date=$(TZ=America/Lima date +%F)"
```

Para detenerlo:

```bash
docker compose -f infra/docker-compose.yml down
```

## Desarrollo

### Backend

Requiere Python 3.12 y [`uv`](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync                                      # resuelve el entorno
uv run python -m datalake.generate_datalake  # regenera el Data Lake canónico
uv run uvicorn app.main:app --reload          # http://127.0.0.1:8000
```

El CSV del Data Lake viene incluido en el repositorio, así que el generador sólo hace
falta si cambian sus reglas. Es determinista: con la misma configuración produce
siempre el mismo archivo.

La configuración tiene valores por omisión funcionales y se ajusta con variables
`MP_`:

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MP_RUTA_DATALAKE` | `backend/datalake/machupicchu_history.csv` | Ruta del CSV del historial. |
| `MP_OPEN_METEO_BASE_URL` | `https://api.open-meteo.com/v1/forecast` | Endpoint del pronóstico. |
| `MP_OPEN_METEO_TIMEOUT` | `4.0` | Segundos de espera antes de un `502`. |
| `MP_CORS_ORIGINS` | `["http://localhost:4200", "http://127.0.0.1:4200"]` | Orígenes permitidos, como JSON. |
| `MP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` o `CRITICAL`. |

Documentación interactiva de la API en <http://127.0.0.1:8000/docs>.

### Frontend

Requiere Node 20.

```bash
cd frontend
npm install
npm start            # http://localhost:4200, con proxy a :8000
```

`proxy.conf.json` reenvía `/api` al backend del puerto 8000, igual que Nginx en
producción. Si el backend vive en otro puerto, se ajusta ese archivo.

## Tests

```bash
# Backend: 286 pruebas, con umbral de cobertura del 80 %.
cd backend && uv run pytest

# Frontend: 78 pruebas en Chrome headless (necesita CHROME_BIN o un Chrome instalado).
cd frontend && npx ng test --watch=false --browsers=ChromeHeadless

# Verificación del Data Lake y la compilación de la aplicación.
cd frontend && npm run build
```

## Estructura

```
backend/
  app/            API FastAPI: Data Lake, clima, predicción y rutas
  datalake/       Generador del historial sintético y el CSV versionado
  tests/          Pruebas del backend
frontend/
  src/app/        SPA Angular: página, tarjeta de resultado y cliente de la API
  nginx/          Configuración de Nginx que sirve la SPA y hace de proxy
infra/
  docker-compose.yml
```

## API

| Ruta | Qué hace |
| --- | --- |
| `GET /api/prediction?date=YYYY-MM-DD` | Predicción de afluencia. Sin `date`, usa hoy en `America/Lima`. |
| `GET /health` | Sonda de salud. No consulta ni el clima ni el Data Lake. |
| `GET /docs` | Documentación OpenAPI interactiva. |

Errores: `422` si la fecha tiene un formato inválido, ya pasó o está fuera de la
ventana del proveedor; `502` si no se puede obtener el pronóstico.
