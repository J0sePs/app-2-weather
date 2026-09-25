# Design

## Context

El repositorio contiene únicamente el contrato funcional (`openspec/project.md`) y
la configuración de OpenSpec. No hay código, ni manifiestos de dependencias, ni
configuración de lint, ni convenciones heredadas. Ver `proposal.md` para la
motivación y los cuatro capabilities de este change.

Restricciones que vienen del contrato y que condicionan el diseño:

- Memoria total de runtime < 400 MB (instancia EC2 t3.micro de 1 GB). El presupuesto
  incluye los dos contenedores, no el build de la imagen.
- El despliegue es de dos servicios: backend y frontend. `project.md` no define
  CORS ni exige multi-usuario ni autenticación, y el frontend se sirve por el mismo
  origen que la API, así que el proxy inverso es el mecanismo natural de integración.
- La única dependencia externa es Open-Meteo, sin API key, con ventana de pronóstico
  limitada y sin garantía de disponibilidad.
- Cobertura mínima del 80% exigida con pytest y `respx` para el mockeo de Open-Meteo.
- Los artefactos (specs, código, comentarios) se escriben en español, siguiendo el
  idioma del contrato.

Decisiones tomadas con el usuario y ya reflejadas en los specs: ventana de pronóstico
acotada con error explícito fuera de rango, Data Lake determinista con época fija, y
marcado de feriados nacionales peruanos en días laborables.

## Goals / Non-Goals

**Goals:**

- Estructura de repositorio de tres directorios (`backend/`, `frontend/`,
  `infra/`) que mapea 1:1 con las capacidades de los specs, de modo que un reader
  pueda localizar el código de cada spec sin consultar el índice.
- Backend con una ruta de código única: la petición va de la capa HTTP a la lógica de
  predicción y de ahí al cliente de clima y al Data Lake, sin estado global mutable
  más allá de la instancia del Data Lake.
- Aislar por completo la dependencia externa detrás de una interfaz propia, de modo
  que los tests de la lógica de predicción no necesiten red ni `respx`.
- Tests que usen el CSV canónico real en lugar de fixtures duplicadas, gracias a la
  determinismo del generador, más unos pocos CSV en línea para los casos de error.
- Build reproducible y despliegue de un solo comando.

**Non-Goals:**

- Modelo predictivo aprendido o series temporales. La estimación es un promedio
  ponderado por similitud, no un ML; añadirlo requeriría otra capacidad.
- Persistencia de predicciones, historial de consultas o accounts de usuario.
- Autenticación, rate limiting o cache de resultados. El único consumidor es una SPA
  de una página.
- Internacionalización. Los textos de la UI y las respuestas de la API están en español
  y se fija el locale `es-PE` en lugar de preparar la app para varios idiomas.
- La API de archivo histórico de Open-Meteo (ver `proposal.md`).
- Tema oscuro, animaciones o librería de componentes.

## Decisions

### 1. Layout del repositorio

```
backend/
  pyproject.toml
  Dockerfile
  app/
    main.py            # fábrica de la app FastAPI y lifespan
    settings.py        # pydantic-settings
    models.py          # modelos pydantic de entrada/salida
    datalake.py        # dataclass del registro + carga y filtros
    weather.py         # cliente de Open-Meteo y mapeo de weathercode
    prediction.py      # selección de días similares y estimación
    routers/
      health.py
      prediction.py
  datalake/
    generate_datalake.py
    machupicchu_history.csv   # artefacto generado, versionado
  tests/
frontend/
  Dockerfile
  nginx/default.conf
  src/app/...
infra/
  docker-compose.yml
```

Racional: el nombre de cada módulo coincide con la capacidad que implementa, y
`routers/` separa el transporte HTTP de la lógica de dominio para que la lógica sea
testeable sin `TestClient`. El CSV se versiona porque es determinista y porque el
contenedor lo necesita en la imagen sin depender de un paso de generación en el
build.

Alternativa descartada: un único `main.py` con todo el backend. Se descartó porque
haría imposible testear la lógica de predicción sin levantar el servidor, y porque
rompe el mapeo con las capacidades.

### 2. Carga del Data Lake en el ciclo de vida de la aplicación

El Data Lake se carga en el `lifespan` de FastAPI y se guarda en `app.state`. La
instancia inmutable se inyecta en el router por `Depends`.

Racional: cumple el requisito de leer el disco una vez y hace que el fallo por CSV
ausente o malformado ocurra en el arranque, que es donde el mensaje que sugiere
ejecutar el generador es útil. `app.state` evita un módulo con singleton global,
que rompería los tests que necesitan dos apps con Data Lakes distintos.

Alternativa descartada: caché con `@lru_cache` a nivel de función. Se descartó
porque difiere el error de arranque y hace imposible el aislamiento entre tests.

### 3. La ventana de pronóstico se deriva de la respuesta, no de una constante

El endpoint pide a Open-Meteo el rango completo de fechas disponible (un solo GET con
`daily=...` sin `start_date`/`end_date`), y la validación de `date` se hace contra las
fechas que el proveedor realmente devolvió en `daily.time`.

Racional: Open-Meteo no publica un contrato de "16 días" y su ventana varía con la
latitud, la estación y su disponibilidad. Leer la ventana de la respuesta hace que
`422` sea siempre correcto sin codificar un número que puede quedar desfasado, y
permite incluir en el mensaje la última fecha realmente consultable. También evita una
segunda llamada a la API para validar.

Alternativa descartada: constante `FORECAST_DAYS = 16` validada en local. Se descartó
porque se desincroniza de la fuente y produce errores falsos en los bordes.

Coste: la validación de `date` depende de una llamada de red. Se acepta: el caso sin
parámetro, que es el más frecuente, y el caso de fecha inválida se rechazan antes de
salir a la red; sólo las fechas bien formadas y no pasadas llegan al proveedor.

### 4. Interfaz propia para el clima, con mapeo explícito de `weathercode`

Un módulo `weather.py` expone una única operación asíncrona que devuelve la previsión
de una fecha como un valor propio (`DailyForecast` con `temperature_max`,
`precipitation_probability`, `condition`). Por debajo usa un `httpx.AsyncClient`
compartido y una tabla explícita `weathercode -> descripción en español`.

Racional: la lógica de predicción depende de una abstracción estable, así que sus
tests no requieren `respx`. La tabla explícita evita depender de un diccionario
externo desactualizado y hace que el mapeo sea una decisión auditable y testeable. Los
códigos desconocidos caen en una descripción genérica en lugar de fallar, porque un
código nuevo de Open-Meteo no debe tumbar la aplicación.

Alternativa descartada: consumir la tabla oficial de Open-Meteo desde su repositorio
en cada arranque. Se descartó por añadir una dependencia de red en el arranque y una
fuente de fallo no relacionada con la predicción.

### 5. Selección de días similares en dos niveles, sin pesos

La estimación se calcula como el promedio simple de `visitantes_reales` de los
registros que coinciden en (condición de fin de semana o feriado, clima compatible) y,
en un segundo nivel relajado, en (condición de fin de semana o feriado, temporada). El
primer nivel que devuelva coincidencias gana.

Racional: un promedio simple es explicable ("esto es lo queseeing pasó de media en días
parecidos"), lo que es valioso en una app cuyo output es un número que un usuario
planifica su viaje. La relajación garantiza que siempre hay base de cálculo sin
inventar datos. La compatibilidad de clima se define por una banda de precipitation
en lugar de por igualdad de categoría: así un `weathercode` de "lluvia ligera" y un
CSV con `lluvia` se comparan, y un día despejado no se compara con una tormenta.

Alternativas descartadas:

- *Vecinos más cercanos (k-NN) sobre un vector de features*: da mejores números en
  principio, pero hace la estimación inexplicable y añade una dependencia. Se
  descartó por el criterio de minimalismo de `project.md`; cabe como cambio futuro
  dentro de esta misma capacidad.
- *Regresión o modelo entrenado sobre el CSV*: mismo motivo, y no justificable con
  datos sintéticos.

### 6. Errores de la API con un manejador único

La dependencia externa y el Data Lake lanzan excepciones de dominio propias
(`WeatherUnavailableError`, `DataLakeError`). Un manejador registrado las traduce a
`502` (clima) con un mensaje apto para el usuario final, y las validaciones de
`target_date` usan el `HTTPException` estándar de FastAPI con `422`.

Racional: el mensaje que ve el usuario lo escribe una persona, no lo infiere un traceback.
El `502` distingue "Open-Meteo está caído" de "el usuario mandó una fecha mala", y la UI
puede tratar ambos con mensajes distintos. La UI ya está especificada para distinguir
`422` de `502`.

### 7. Zona horaria `America/Lima` y `tzdata` en la imagen

Toda comparación de fechas usa `ZoneInfo("America/Lima")`, y el Dockerfile del
backend instala el paquete `tzdata` del sistema.

Racional: "hoy" para un sitio en Cusco no es "hoy" en UTC; sin esto, entre las 20:00
y las 24:00 de Lima la fecha por omisión sería un día atrás y toda consulta
devolvería `422`. `python:3.12-slim` no incluye la base de datos IANA, así que sin
instalar `tzdata` el proceso falla en tiempo de ejecución con un error que no aparece
en los tests de la máquina de desarrollo. Se documenta explícitamente porque es el
fallo más fácil de no detectar antes del despliegue.

Alternativa descartada: fijar `TZ=UTC` y restar 5 horas a mano. Se descartó por
fragilidad y por no ser explícito.

### 8. URL de la API en el frontend como ruta relativa

La URL base de la API es la ruta relativa `/api` en un `InjectionToken` de Angular, sin
inyección en tiempo de ejecución ni `environment.prod.ts` con un host absoluto.

Racional: es lo que hace funcionar el mismo build detrás de Nginx (proxy) y en `ng
serve` con un `proxy.conf.json` en desarrollo, sin recompilar para cada entorno. Evita
el anti-patrón del `config.json` de runtime que Angular ya no incluye por defecto.

### 9. `proxy_pass` sin ruta, y fallback de SPA

La configuración de Nginx usa `location /api/ { proxy_pass http://backend:8000; }` (sin
ruta final), que preserva la URI completa, más `try_files $uri $uri/ /index.html;`.

Racional: es el patrón correcto para proxear prefijo en Nginx; poner
`proxy_pass http://backend:8000/;` eliminaría el prefijo `/api` y rompería las rutas
del backend. El `try_files` es necesario para que el enrutado del cliente sobreviva a
un F5. Se añade `proxy_set_header Host $host` y timeouts para que el backend vea un
requestHeaders coherente.

### 10. CORS present pero sin efecto en producción

Se incluye `CORSMiddleware` con los orígenes coming de la configuración (por defecto
todos en desarrollo), pero el despliegue de Compose no lo necesita porque Nginx sirve
ambos en el mismo origen.

Racional: sin esto, `ng serve` en desarrollo (puerto 4200) contra el backend (puerto
8000) fallaría por CORS, y eso es un tropiezo diario. Se mantiene la config porque es
gratis, pero el diseño no debe depender de ella: si alguien despliega el backend solo,
el error debe ser visible y no silenciosamente tolerado.

Alternativa descartada: no añadir CORS y usar siempre el proxy también en desarrollo.
Se descartó porque obliga a levantar Nginx para iterar el frontend.

### 11. Pruebas contra el CSV canónico, con el umbral de cobertura en el backend

`tests/` usa el CSV generado real (determinista) para los tests de predicción y de
lógica de negocio, y CSV en línea mínimos para los casos de carga fallida. El cliente
de clima se prueba con `respx` interceptando `httpx`; la lógica de predicción se
prueba con un doble de la interfaz de clima, sin red. La suite corre con
`pytest-asyncio` y `httpx.ASGITransport` para ejercitar los endpoints sin servidor.

El `--cov-fail-under=80` se mide sólo sobre el paquete `app`, excluyendo el generador
del Data Lake (es código de preparación de datos ejecutado bajo demanda, no código de
runtime; incluirlo bajaría la métrica sin reflejar calidad del servicio).

Racional: usar el CSV real evita que los fixtures se desincronicen del generador, que es
el modo de fallo clásico cuando el dataset lo produce código. `ASGITransport` prueba
el enrutamiento, los códigos de estado y el esquema de la respuesta sin abrir un puerto.

### 12. Sin reintentos ni caché en el cliente externo

Una única petición a Open-Meteo por consulta, con timeout configurable (4 s por
omisión) y sin reintentos.

Racional: la respuesta suele tardar menos de 500 ms y un reintento multiplica el peor
caso de latencia de una UI que el usuario percibe como lentitud. El usuario puede
volver a pulsar, que es la semántica correcta para un dato que cambia por horas. La
ventana de error de 4 s está por debajo de la percepción de "se ha colgado".

### 13. VERSIONado del CSV y su dependencia de la imagen

El CSV se versiona en el repositorio y se copia en la imagen con `COPY`. El
contentenedor no regenera el dataset al arrancar.

Racional: el build queda reproducible y el contenedor no necesita escribir en su
sistema de archivos, lo que permite ejecutarlo con el filesystem de sólo lectura. La
regeneración es una tarea explícita de desarrollo (`generate_datalake`).

## Risks / Trade-offs

- **El historial es sintético, no conteos reales** → La estimación puede desviarse de
  la realidad. Mitigación: la UI muestra un aviso visible de que los datos son de
  demostración (requisito en `prediction-web-ui`), y el CSV no se presenta como fuente
  oficial en ningún punto del API. Cuando exista data real, el cambio queda contenido
  en la capacidad `data-lake`: se sustituye el generador por un ingest real.
- **Open-Meteo cambia la forma de su respuesta JSON** → Rompe el cliente y devuelve
  `502` en vez de un 5xx opaco. Mitigación: el cliente valida la presencia de las
  claves esperadas y traduce el fallo a `WeatherUnavailableError`; los tests con `respx`
  fijan un ejemplo de payload real, así que un cambio de forma lo detecta la suite.
- **La ventana de pronóstico se acorta cerca de fin de mes** → Un usuario ve `422` para
  una fecha que ayer consultaba. Mitigación: el mensaje de error nombra la última fecha
  consultable, y la UI lo muestra tal cual en lugar de un error genérico.
- **Sin `tzdata` en la imagen, la validación de fechas falla en runtime** → Fallo en
  producción y no en los tests locales. Mitigación: el Dockerfile instala `tzdata`
  explícitamente y hay un test de la ruta `GET /api/prediction` sin `date` que ejercita
  `ZoneInfo("America/Lima")`; la imagen se levanta en el smoke test de despliegue.
- **El CSV generador y el backend pueden desincronizarse** → Un cambio en las reglas de
  negocio sin regenerar deja tests y datos incoherentes. Mitigación: los tests de las
  reglas de negocio leen el CSV versionado, así que fallan si el generador cambia sin
  regenerar, lo que convierte la desincronización en un fallo visible de CI.
- **El presupuesto de 400 MB es una estimación, no una medición** → El runtime real
  de uvicorn + Python con el Data Lake en memoria es de decenas de MB y Nginx
  ocupa unos pocos MB, pero el valor concreto no está medido. Mitigación: el
  `docker-compose.yml` no fija límites duros; medir `docker stats` en el smoke test
  y ajustar si aparece cualquier desviación relevante. Si el presupuesto resultara
  insuficiente, el Data Lake completo (730 registros, muy pequeño) no es el culpable.
- **CORS abierto por omisión** → Si alguien despliega el backend con su URL real
  queda EXPERIMENTAL. Mitigación: el valor por omisión es una lista explícita
  localhost, no comodín, y la documentación señala que en Compose la protección es el
  proxy de Nginx.
- **El fallback de clima relajado puede sesgar la estimación** → Cuando ninguna
  categoría climática coincide, el promedio ignora el clima y el número es
  sistemáticamente más alto (temporada seca) o más bajo. Mitigación: el relajado sólo
  actúa cuando el filtro estricto no encuentra nada, y la clasificación del clima
  cubre todo el espectro de `weathercode` para que el caso sea raro.

## Migration Plan

Proyecto greenfield: no hay datos, usuarios ni despliegue previo que migrar.

Puesta en marcha en entorno nuevo:

1. `uv sync` en `backend/` para resolver el entorno de desarrollo.
2. `uv run python -m datalake.generate_datalake` para materializar el CSV (idempotente;
   en un clon nuevo puede omitirse si el CSV ya está versionado).
3. `pytest` para validar la lógica contra el CSV canónico y el umbral de cobertura.
4. `docker compose -f infra/docker-compose.yml up --build` para levantar el conjunto.
5. Smoke test: `curl http://localhost/health` y `curl
   "http://localhost/api/prediction?date=<hoy>"`, más `docker stats` para confirmar el
   presupuesto de memoria.

Rollback: al no haber estado previo, el rollback es eliminar el directorio de trabajo y
volver a clonar. Si sólo falla una imagen, `docker compose up --build` reconstruye desde
los Dockerfiles sin estado que restaurar.

## Open Questions

Ninguna que afecte a los specs, al enfoque o al desglose de tareas. Las decisiones
pendientes que surgieron durante la exploración (qué tan completa sea la tabla de
feriados, si el presupuesto de memoria real deja margen) son ajustes de datos
locales, no cambios de comportamiento observable, y pueden resolverse durante la
implementación sin tocar estos artefactos.
