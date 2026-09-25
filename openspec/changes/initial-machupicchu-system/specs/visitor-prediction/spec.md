# Spec Delta

## Purpose

Capacidad de estimar la afluencia de turistas a Machu Picchu para una fecha
concreta, cruzando el pronóstico meteorológico real de Open-Meteo con el historial del
Data Lake, y exponiendo el resultado a través de una API HTTP con dos endpoints
(`GET /api/prediction` y `GET /health`).

## ADDED Requirements

### Requirement: Consulta del pronóstico meteorológico
El sistema SHALL obtener el pronóstico diario para las coordenadas de Machu Picchu
(`latitude=-13.1631`, `longitude=-72.5450`) del endpoint público de Open-Meteo, sin
requerir credenciales, y SHALL solicitar las variables diarias de temperatura máxima,
probabilidad máxima de precipitación y código de condición atmosférica.

El sistema SHALL traducir el código numérico de condición atmosférica a una
descripción legible en español, de modo que la respuesta nunca exponga un entero
crudo como texto de condición.

El sistema SHALL invocar a Open-Meteo una sola vez por consulta de predicción, con las
coordenadas de Machu Picchu fijadas por el sistema y no aportadas por el cliente.

#### Scenario: Pronóstico obtido correctamente
- **WHEN** el sistema consulta el pronóstico para una fecha dentro de la ventana soportada
- **THEN** obtiene la temperatura máxima, la probabilidad de precipitación y la condición atmosférica asociadas a esa fecha

#### Scenario: Traducción de la condición atmosférica
- **WHEN** Open-Meteo devuelve un código de condición atmosférica conocido
- **THEN** el sistema lo expone como una descripción en español, y no como el código numérico

#### Scenario: Las coordenadas no son controlables por el cliente
- **WHEN** un cliente intenta influir en la latitud o longitud de la consulta
- **THEN** la petición a Open-Meteo sigue usando las coordenadas de Machu Picchu definidas por el sistema

#### Scenario: Fallo del proveedor externo
- **WHEN** Open-Meteo responde con un error o no responde dentro del tiempo de espera configurado
- **THEN** el sistema responde con estado HTTP 502 e informa que no se pudo obtener el pronóstico, sin devolver datos de clima inventados ni un error 500 genérico

### Requirement: Validación de la fecha objetivo
`GET /api/prediction` SHALL aceptar un parámetro de consulta opcional `date` en
formato `YYYY-MM-DD`. Si `date` se omite, el sistema SHALL usar la fecha actual en la
zona horaria del sitio (`America/Lima`).

El sistema SHALL rechazar con estado HTTP 422 y un mensaje que nombre el rango
soportado:

- cualquier valor de `date` que no sea una fecha válida en formato `YYYY-MM-DD`;
- cualquier fecha anterior a la fecha actual en `America/Lima`;
- cualquier fecha posterior al último día disponible en la ventana de pronóstico de
  Open-Meteo.

El sistema SHALL NOT inventar datos de clima fuera de esa ventana ni recurrir a la API
de archivo histórico de Open-Meteo: fuera de rango la consulta es un error de
validación, no una estimación.

#### Scenario: Fecha por omisión
- **WHEN** se llama a `GET /api/prediction` sin el parámetro `date`
- **THEN** el sistema usa la fecha actual en `America/Lima` como fecha objetivo y devuelve la predicción correspondiente

#### Scenario: Fecha explícita dentro de la ventana
- **WHEN** se llama a `GET /api/prediction?date=` con una fecha válida dentro de la ventana de pronóstico
- **THEN** el sistema devuelve la predicción para esa fecha

#### Scenario: Formato de fecha inválido
- **WHEN** se llama a `GET /api/prediction?date=26-09-2026`
- **THEN** el sistema responde con estado HTTP 422 y un mensaje que indica que se espera el formato `YYYY-MM-DD`

#### Scenario: Fecha pasada
- **WHEN** se llama a `GET /api/prediction?date=` con una fecha anterior a la fecha actual en `America/Lima`
- **THEN** el sistema responde con estado HTTP 422 e indica que sólo se admiten fechas desde hoy

#### Scenario: Fecha fuera de la ventana de pronóstico
- **WHEN** se llama a `GET /api/prediction?date=` con una fecha posterior al último día de la ventana de pronóstico
- **THEN** el sistema responde con estado HTTP 422 e indica cuál es la última fecha consultable

### Requirement: Cálculo de la estimación de visitantes
El sistema SHALL estimar el número de visitantes cruzando el clima prognosis de la
fecha objetivo con los registros del Data Lake, mediante un promedio de los
visitantes reales de los días que coinciden en las dimensiones relevantes.

El algoritmo de selección de días similares SHALL:

1. determinar la temporada de la fecha objetivo a partir de su mes;
2. determinar si la fecha objetivo es sábado, domingo, feriado nacional peruano o día
   laborable no feriado, replicando el mismo criterio con el que el Data Lake marca
   `es_fin_de_semana_o_feriado`;
3. filtrar el Data Lake por esa condición de fin de semana o feriado y por la
   coherencia entre el clima prognosis y las categorías climáticas del Data Lake, de
   modo que un día con lluvia torrencial o tormenta se compare contra días de mal
   tiempo y un día despejado contra días benignos;
4. calcular el promedio de `visitantes_reales` de los registros coincidentes.

Si el filtro por clima no devuelve coincidencias, el sistema SHALL relajar el criterio
y calcular el promedio usando únicamente la condición de fin de semana o feriado y la
temporada, de modo que siempre exista una base de cálculo. El sistema SHALL NOT
devolver una estimación cuando no exista ninguna coincidencia ni con el filtro
relajado.

La estimación SHALL estar acotada al rango de 0 a 5,600 visitantes, que es la
capacidad máxima oficial del sitio.

#### Scenario: Día laborable de buen tiempo
- **WHEN** se consulta un día laborable no feriado con clima benigno en temporada seca
- **THEN** la estimación se calcula a partir del promedio de los días laborables no feriado de temporada seca con clima benigno

#### Scenario: Fin de semana con más afluencia
- **WHEN** se consulta un sábado o domingo y se compara con la estimación de un día laborable no feriado equivalente en temporada y clima
- **THEN** la estimación del fin de semana es mayor que la del día laborable

#### Scenario: Feriado en día laborable con más afluencia
- **WHEN** se consulta un feriado nacional peruano que cae de lunes a viernes y se compara con un día laborable no feriado equivalente en temporada y clima
- **THEN** la estimación del feriado es mayor que la del día laborable no feriado

#### Scenario: Mal tiempo reduce la estimación
- **WHEN** se consulta un día con lluvia torrencial o tormenta y se compara con un día de buen tiempo de la misma temporada y condición de fin de semana o feriado
- **THEN** la estimación del día de mal tiempo es menor que la del día de buen tiempo

#### Scenario: Relajación del filtro climático
- **WHEN** el clima prognosis no coincide con ninguna categoría climática del Data Lake para esa fecha objetivo
- **THEN** el sistema calcula el promedio usando los días de la misma temporada y condición de fin de semana o feriado, sin devolver un error

#### Scenario: La estimación respeta el aforo máximo
- **WHEN** el promedio de los registros coincidentes supera los 5,600 visitantes
- **THEN** la estimación devuelta es 5,600

### Requirement: Cálculo de la capacidad y el nivel de afluencia
El sistema SHALL derivar del número estimado de visitantes:

- `capacity_percentage` = estimados / 5,600 × 100, redondeado a un decimal;
- `crowd_level`, que SHALL ser `Bajo` si los estimados son menos de 3,000,
  `Moderado` si están entre 3,000 y 4,500 incluidos ambos extremos, y `Alto` si
  superan 4,500.

#### Scenario: Nivel Bajo
- **WHEN** la estimación es de 2,400 visitantes
- **THEN** `crowd_level` es `Bajo`

#### Scenario: Nivel Moderado en el extremo inferior
- **WHEN** la estimación es exactamente 3,000 visitantes
- **THEN** `crowd_level` es `Moderado`

#### Scenario: Nivel Moderado en el extremo superior
- **WHEN** la estimación es exactamente 4,500 visitantes
- **THEN** `crowd_level` es `Moderado`

#### Scenario: Nivel Alto
- **WHEN** la estimación es de 4,580 visitantes
- **THEN** `crowd_level` es `Alto` y `capacity_percentage` es 81.8

#### Scenario: Consistencia del porcentaje
- **WHEN** se devuelve una predicción
- **THEN** `capacity_percentage` es `estimated_visitors` dividido entre 5,600 por 100, redondeado a un decimal

### Requirement: Contrato de la respuesta de predicción
`GET /api/prediction` SHALL responder con estado HTTP 200 y un objeto JSON con esta
forma exacta:

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

- `site` SHALL ser siempre la cadena `Machu Picchu`.
- `target_date` SHALL ser la fecha consultada en formato `YYYY-MM-DD`.
- `weather.temperature_max` SHALL expresarse en grados Celsius.
- `weather.precipitation_probability` SHALL ser un porcentaje entero entre 0 y 100.
- `weather.condition` SHALL ser una descripción en español.
- `prediction.estimated_visitors` SHALL ser un entero.
- `prediction.crowd_level` SHALL ser uno de `Bajo`, `Moderado` o `Alto`.

La respuesta SHALL incluir la cabecera `Content-Type: application/json`.

#### Scenario: Forma de la respuesta correcta
- **WHEN** se consulta una fecha válida y Open-Meteo responde correctamente
- **THEN** el cuerpo es JSON con las claves `site`, `target_date`, `weather` y `prediction`, sin claves adicionales
- **AND** `weather` contiene `temperature_max`, `precipitation_probability` y `condition`
- **AND** `prediction` contiene `estimated_visitors`, `capacity_percentage` y `crowd_level`

#### Scenario: Encabezado de contenido
- **WHEN** se recibe una predicción correcta
- **THEN** la cabecera `Content-Type` es `application/json`

#### Scenario: El cliente controla la fecha, no el sitio
- **WHEN** un cliente consulta una fecha distinta de la actual
- **THEN** `site` sigue siendo `Machu Picchu` y `target_date` es la fecha solicitada

### Requirement: Endpoint de salud
El sistema SHALL exponer `GET /health` que responda con estado HTTP 200 y el cuerpo
JSON `{"status": "ok"}`. Este endpoint SHALL NOT depender de Open-Meteo ni de la
disponibilidad del Data Lake, para que los orquestadores puedan comprobar la salud del
proceso sin consumir la API externa.

#### Scenario: Sonda de salud satisfactoria
- **WHEN** se llama a `GET /health`
- **THEN** el sistema responde con estado HTTP 200 y el cuerpo `{"status": "ok"}`

#### Scenario: La sonda de salud no consume la API externa
- **WHEN** se llama a `GET /health` con Open-Meteo inaccesible
- **THEN** el sistema responde igualmente con estado HTTP 200 y `{"status": "ok"}`, sin realizar ninguna petición a Open-Meteo

### Requirement: Documentación interactiva de la API
El sistema SHALL exponer la documentación interactiva y el esquema OpenAPI en las
rutas por defecto de FastAPI (`/docs` y `/openapi.json`) sin protección adicional,
para que la API sea descubrible durante el desarrollo.

#### Scenario: Documentación accesible
- **WHEN** se solicita `GET /openapi.json`
- **THEN** el sistema responde con estado 200 y el esquema OpenAPI, que declara los endpoints `/api/prediction` y `/health`

### Requirement: Configuración por variables de entorno
El sistema SHALL leer su configuración de variables de entorno mediante un mecanismo
de settings tipado, de modo que el Data Lake, la URL base de Open-Meteo, el tiempo de
espera de la petición externa y el nivel de log sean ajustables sin tocar el código.
Los valores por defecto SHALL ser funcionales sin configurar ninguna variable.

#### Scenario: Valores por defecto funcionales
- **WHEN** el backend se ejecuta sin definir ninguna variable de entorno propia
- **THEN** localiza el Data Lake en su ruta por defecto, consulta la URL pública de Open-Meteo y arranca correctamente

#### Scenario: Anulación por variable de entorno
- **WHEN** se define la variable que apunta al Data Lake con otra ruta
- **THEN** el sistema carga el archivo de esa ruta en lugar del de por defecto
