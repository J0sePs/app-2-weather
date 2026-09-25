# Tasks

## 1. Andamiaje del repositorio

- [x] 1.1 Crear la estructura de directorios `backend/app/routers/`, `backend/datalake/`, `backend/tests/`, `frontend/`, `infra/` y verificar que `find . -type d` devuelve cada una de ellas
- [x] 1.2 Declarar el proyecto Python en `backend/pyproject.toml` con FastAPI, uvicorn, httpx, pydantic, pydantic-settings y el paquete `app`, y verificar con `uv sync` que se resuelve sin errores
- [x] 1.3 Declarar en `backend/pyproject.toml` el grupo de desarrollo con pytest, pytest-asyncio, pytest-cov, respx y httpx, y verificar con `uv run pytest --collect-only` que el runner arranca
- [x] 1.4 Configurar en `backend/pyproject.toml` (o en el archivo de configuración de pytest equivalente) `--cov=app --cov-fail-under=80`, y verificar que una suite vacía falla con el umbral y que una suite con un test trivial también lo hace

## 2. Data Lake: generación del CSV sintético

- [x] 2.1 Implementar el catálogo fijo de feriados nacionales peruanos y las funciones de fecha en español, día de la semana, temporada (seca may-oct / lluvias nov-abr) y clima, y verificar con tests unitarios que 2026-06-24 y 2026-07-28 se reconocen como feriado, que 2026-06-28 es domingo y que el mes de abril da temporada `lluvias`
- [x] 2.2 Implementar el generador con época de inicio fija y `random.Random` con semilla fija, aplicando la base por temporada, el +15% de fin de semana o feriado y la reducción por lluvia torrencial o tormenta, y verificar que el máximo de `visitantes_reales` no supera 5,600
- [x] 2.3 Exponer el generador como módulo ejecutable con opciones de ruta de salida y fecha de inicio, y verificar que `uv run python -m datalake.generate_datalake` sin argumentos escribe en `backend/datalake/machupicchu_history.csv`
- [x] 2.4 Ejecutar el generador dos veces con la misma configuración y verificar con `sha256sum` que ambos archivos son idénticos byte a byte
- [x] 2.5 Escribir los tests de las reglas de negocio que leen el CSV versionado (media seca > media lluvias con diferencia ≥ 1,000; rangos 4,000-5,200 y 1,800-3,200; mal tiempo por debajo de buen tiempo; feriados en día laborable por encima de laborables no feriado; 730 filas con fechas consecutivas) y verificar que pasan contra el CSV generado
- [x] 2.6 Versionar el CSV generado en el repositorio y verificar que `git status` lo muestra como añadido y que `.gitignore` no lo excluye

## 3. Data Lake: carga y consulta

- [x] 3.1 Implementar el modelo de registro y la carga única del CSV con validación de encabezados, y verificar que cargarlo con un CSV de encabezados incorrectos lanza `DataLakeError` nombrando la columna faltante
- [x] 3.2 Verificar el fallo por archivo ausente: cargar una ruta inexistente produce `DataLakeError` que nombra la ruta y sugiere el comando del generador
- [x] 3.3 Implementar los filtros por días de la semana, categorías climáticas, temporadas, condición de fin de semana o feriado y fecha exacta, y verificar con tests que los filtros devuelven sólo registros coincidentes, que un filtro sin coincidencias devuelve lista vacía sin excepción y que la media del conjunto `true` de fin de semana o feriado supera la del `false`
- [x] 3.4 Cargar el Data Lake en el `lifespan` de la aplicación y guardarlo en `app.state`, y verificar con un test que dos aplicaciones creadas en el mismo proceso pueden usar Data Lakes distintos

## 4. Cliente de clima Open-Meteo

- [x] 4.1 Implementar el mapeo de `weathercode` a descripción en español con fallback genérico para códigos desconocidos, y verificar con tests parametrizados que los códigos representativos de sol, nubes, lluvia y tormenta producen las descripciones esperadas y que un código inventado no lanza excepción
- [x] 4.2 Implementar la consulta de pronóstico con las coordenadas fijas de Machu Picchu y un timeout configurable, y verificar con `respx` que la URL enviada contiene `latitude=-13.1631`, `longitude=-72.5450`, las variables `daily` requeridas y `timezone=America/Lima`
- [x] 4.3 Verificar con `respx` los casos de fallo: timeout, error de estado y payload sin las claves esperadas levantan `WeatherUnavailableError` en lugar de propagar la excepción de `httpx`
- [x] 4.4 Verificar con `respx` que la función devuelve las fechas realmente disponibles en `daily.time`, para que la ventana de pronóstico se derive de la respuesta del proveedor

## 5. Lógica de predicción

- [x] 5.1 Implementar la clasificación de la condición de fin de semana o feriado de la fecha objetivo reutilizando el mismo criterio y catálogo que el Data Lake, y verificar con tests que un sábado, un domingo, el 24 de junio y un miércoles ordinario se clasifican correctamente
- [x] 5.2 Implementar la traducción de la previsión del día a las categorías climáticas del Data Lake mediante bandas de probabilidad de precipitación, y verificar con tests que lluvia torrencial o tormenta no se comparan con un día despejado
- [x] 5.3 Implementar la selección de días similares en dos niveles (estricto con clima, relajado con temporada) y el promedio de visitantes, y verificar con tests usando un doble de la interfaz de clima que un sábado seco estima por encima de un miércoles seco y que un día de tormenta estima por debajo
- [x] 5.4 Verificar el relajado: cuando la categoría climática no encuentra coincidencias, la estimación se calcula igual con la temporada y la condición de fin de semana, sin error
- [x] 5.5 Verificar que la estimación está acotada a [0, 5600] y que los niveles de afluencia son `Bajo` por debajo de 3,000, `Moderado` entre 3,000 y 4,500 ambos incluidos, y `Alto` por encima de 4,500, con casos de prueba en los límites exactos

## 6. API HTTP

- [x] 6.1 Implementar los modelos de respuesta con el esquema de `visitor-prediction` (sitio, fecha objetivo, clima y predicción) y verificar que un ejemplo válido se serializa con exactamente esas claves
- [x] 6.2 Implementar `GET /health` con dependencia cero de Open-Meteo y del Data Lake, y verificar con un test que responde 200 y `{"status":"ok"}` con ambos subsistemas inservibles
- [x] 6.3 Implementar `GET /api/prediction` con parámetro opcional `date`, omisión por defecto a la fecha actual en `America/Lima`, y rechazo con 422 de formato inválido y de fecha pasada, verificado con tres tests de endpoint
- [x] 6.4 Implementar el rechazo con 422 de fecha fuera de la ventana, tomando la última fecha del mensaje de las fechas devueltas por Open-Meteo, y verificar que el mensaje nombra esa última fecha consultable
- [x] 6.5 Registrar el manejador que traduce `WeatherUnavailableError` a 502 con mensaje apto para el usuario final, y verificar que un fallo de Open-Meteo produce 502 y no 500
- [x] 6.6 Añadir `CORSMiddleware` con orígenes CORS tomados de la configuración, y verificar que un `Origin` permitido recibe cabeceras de CORS y uno no permitido no las recibe
- [x] 6.7 Implementar la configuración con `pydantic-settings` (ruta del Data Lake, URL base de Open-Meteo, timeout, orígenes CORS, nivel de log) con valores por defecto funcionales, y verificar que la app arranca sin definir ninguna variable
- [x] 6.8 Verificar el contrato completo: `GET /openapi.json` responde 200 y declara `/api/prediction` y `/health`, y que una respuesta correcta lleva `Content-Type: application/json`

## 7. Suite de pruebas del backend

- [x] 7.1 Configurar la suite para ejercitar los endpoints con `httpx.ASGITransport` y `pytest-asyncio`, sin abrir puertos, y verificar que un test de endpoint contra un doble de Open-Meteo pasa
- [x] 7.2 Cubrir con tests los escenarios de error de la API (422 de formato, 422 de fecha pasada, 422 fuera de ventana, 502 de clima) y verificar que cada test falla si se cambia el código de estado esperado
- [x] 7.3 Cubrir con tests los escenarios de éxito de `/api/prediction` (fecha explícita, fecha por omisión, forma exacta de la respuesta, tipo de contenido) y verificar que la suite pasa
- [x] 7.4 Ejecutar `uv run pytest --cov=app --cov-report=term-missing` y verificar que la cobertura de `app` alcanza al menos el 80%, rellenando los huecos que el informe señale en lugar de añadir `pragma: no cover`

## 8. Frontend Angular

- [x] 8.1 Generar el proyecto Angular 20 en `frontend/` con `ng new`, standalone components, sin SSR, con routing mínimo y con la infraestructura de pruebas del esqueleto, y verificar que `npm run build` produce `dist/` sin errores
- [x] 8.2 Configurar el `InjectionToken` de URL base de la API con la ruta relativa `/api` y un `proxy.conf.json` para `ng serve`, y verificar que en desarrollo la petición llega al backend
- [x] 8.3 Implementar la estructura de la página (encabezado, barra de control, área de resultado) con CSS propio responsivo, y verificar que a 360 px de ancho no hay scroll horizontal ni solapamientos
- [x] 8.4 Implementar el input nativo de fecha inicializado a la fecha actual en `America/Lima`, y verificar con un test que el valor inicial es el formato `YYYY-MM-DD` de hoy
- [x] 8.5 Implementar el servicio de consulta con `HttpClient` y la tarjeta de resultado con clima, visitantes con separador de miles y la palabra "personas", porcentaje de aforo, barra de capacidad y etiqueta de nivel derivada de `crowd_level`, y verificar con tests los tres valores de `crowd_level`
- [x] 8.6 Implementar la sustitución de resultados: una segunda consulta reemplaza las cifras de la primera, y verificar con un test que tras dos consultas la tarjeta muestra los valores de la segunda
- [x] 8.7 Implementar el aviso visible de que el historial es sintético, y verificar con un test que el aviso está presente en pantalla junto a una predicción
- [x] 8.8 Implementar el estado de carga con botón deshabilitado y los tres tratamientos de error (422, 502, fallo de red) con botón rehabilitado y sin tarjeta de resultado, y verificar con tests los tres mensajes

## 9. Contenedores y despliegue

- [x] 9.1 Escribir `backend/Dockerfile` sobre `python:3.12-slim` que instale `tzdata`, copie el código y el CSV, cree un usuario sin privilegios y arranque uvicorn en el puerto 8000, y verificar con `docker build` que la imagen contiene el CSV en la ruta esperada
- [x] 9.2 Verificar que el contenedor del backend arranca sin root y responde `{"status":"ok"}` en `GET /health`
- [x] 9.3 Escribir `frontend/Dockerfile` multi-etapa `node:20-alpine` a `nginx:1.27-alpine` con build de Angular y copia sólo de `dist/` más la configuración de Nginx, y verificar con `docker history` o una inspección equivalente que la imagen final no contiene `node_modules`
- [x] 9.4 Escribir `frontend/nginx/default.conf` con `location /api/` y `proxy_pass` sin ruta final, cabeceras `Host`/`X-Forwarded-*` y timeouts, más `try_files $uri $uri/ /index.html`, y verificar que el smoke test de `9.5` pasa
- [x] 9.5 Levantar el conjunto con `docker compose -f infra/docker-compose.yml up --build` y verificar que `curl http://localhost/api/prediction?date=<hoy>` devuelve la predicción desde el mismo origen que sirve la UI
- [x] 9.6 Verificar que el servicio `backend` no publica puertos en el host y que `frontend` publica el 80, y que declarar `depends_on` hace que `frontend` arranque después de `backend`
- [x] 9.7 Verificar que el enrutado del cliente sobrevive a una recarga en una ruta de la SPA servida por Nginx, y que el proxy devuelve el estado original de la API
- [x] 9.8 Medir con `docker stats` la suma de memoria residente de ambos contenedores y verificar que es inferior a 400 MB
- [x] 9.9 Añadir un README breve con los comandos de desarrollo, de tests y de despliegue, y verificar que un lector puede llegar desde el clon hasta `docker compose up` siguiendo sólo ese README

## 10. Verificación integral

- [x] 10.1 Ejecutar la suite completa del backend y la del frontend en un clon limpio y verificar que ambas pasan, con la cobertura del backend por encima del 80%
- [x] 10.2 Regenerar el Data Lake desde cero y verificar que el CSV resultante no produce diferencias en `git status`, confirmando la reproducibilidad del dataset versionado
- [x] 10.3 Recorrer manualmente el flujo de usuario completo en el navegador (elegir fecha, consultar, ver la tarjeta, provocar un 422 con una fecha fuera de rango, volver a consultar) y verificar que cada paso coincide con el spec de `prediction-web-ui`
