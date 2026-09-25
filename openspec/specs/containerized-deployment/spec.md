# containerized-deployment Specification

## Purpose

Empaquetado y despliegue del sistema de predicción de Machu Picchu como dos servicios
contenedores coordinados por Docker Compose: un backend FastAPI en Python y un
frontend Angular servido por Nginx que hace de proxy inverso hacia la API.

## Requirements

### Requirement: Imagen del backend
El sistema SHALL proveer una imagen de contenedor del backend construida sobre
`python:3.12-slim`, que instale las dependencias declaradas en el manifiesto del
proyecto usando el gestor de paquetes del proyecto, que copie el código de
aplicación y el Data Lake, y que arranque el servidor ASGI escuchando en el puerto
8000 dentro del contenedor.

La imagen SHALL ejecutarse como un usuario sin privilegios de root. El comando de
arranque SHALL ser reproducible a partir de los archivos del repositorio y SHALL NOT
requerir pasos manuales.

#### Scenario: La imagen arranca el servidor
- **WHEN** se construye la imagen del backend y se arranca su contenedor
- **THEN** el proceso del servidor escucha en el puerto 8000 del contenedor y responde a `GET /health`

#### Scenario: El Data Lake está disponible en la imagen
- **WHEN** se inspecciona la imagen construida del backend
- **THEN** contiene el archivo CSV del Data Lake en la ruta que el backend espera por defecto

#### Scenario: Ejecución sin root
- **WHEN** se consulta el usuario con el que se ejecuta el proceso del contenedor del backend
- **THEN** no es `root`

### Requirement: Imagen del frontend con Nginx
El sistema SHALL proveer una imagen de contenedor del frontend construida en dos
etapas: una etapa de compilación sobre `node:20-alpine` que instala las dependencias
y produce los artefactos estáticos de Angular, y una etapa final sobre
`nginx:1.27-alpine` que contiene únicamente los archivos estáticos, la configuración
de Nginx y el código fuente de la aplicación no se incluye en la imagen final.

El servidor SHALL servir la aplicación en el puerto 80 y SHALL dirigir las peticiones
a rutas `/api/*` al servicio backend, de modo que el navegador use un único origen y
no requiera CORS.

La configuración de Nginx SHALL resolver los recursos de la SPA a `index.html` para
que el enrutado del cliente funcione al recargar la página en cualquier ruta.

#### Scenario: Construcción multi-etapa
- **WHEN** se construye la imagen del frontend
- **THEN** la imagen final está basada en `nginx:1.27-alpine` y no contiene `node_modules` ni el código fuente de la aplicación

#### Scenario: La aplicación se sirve por HTTP
- **WHEN** se solicita la raíz del servicio frontend
- **THEN** el servidor responde con estado 200 y el documento HTML de la aplicación

#### Scenario: Proxy hacia la API
- **WHEN** el navegador solicita `GET /api/prediction` a través del host del frontend
- **THEN** Nginx reenvía la petición al backend y devuelve al cliente la respuesta JSON de la API con su estado original
- **AND** el navegador no necesita CORS porque la petición es del mismo origen

#### Scenario: Rutas del cliente tras recargar
- **WHEN** un usuario recarga la página en una ruta de la SPA
- **THEN** Nginx devuelve `index.html` en lugar de un error 404

### Requirement: Orquestación con Docker Compose
El sistema SHALL proveer un archivo `infra/docker-compose.yml` que defina
exactamente los servicios `backend` y `frontend`, con una imagen de cada uno,
construida desde su Dockerfile correspondiente.

El servicio `backend` SHALL exponer el puerto 8000 únicamente en el puerto interno de la
red de Compose: su puerto SHALL NOT publicarse en el host. El servicio `frontend`
SHALL publicar el puerto 80 del host. El servicio `frontend` SHALL declarar
dependencia del servicio `backend` para que el proxy no se publique antes de que la
API esté disponible.

El conjunto completo SHALL mantener su memoria total de runtime por debajo de 400 MB
en condiciones normales de uso, para ser viable en una instancia EC2 t3.micro de
1 GB de RAM.

#### Scenario: Sólo el frontend publica puertos
- **WHEN** se inspecciona la configuración de puertos de los servicios
- **THEN** el servicio `frontend` publica el puerto 80 del host y el servicio `backend` no publica ningún puerto al host

#### Scenario: Orden de arranque
- **WHEN** se levanta el conjunto con Docker Compose
- **THEN** el servicio `frontend` se declara como dependiente del servicio `backend` y ambos alcanzan estado activo

#### Scenario: Flujo extremo a extremo por un único origen
- **WHEN** con el conjunto levantado, un navegador abre el host del frontend y consulta la previsión
- **THEN** la respuesta se obtiene por el mismo origen sin exigir configuración CORS en el backend

#### Scenario: Consumo de memoria dentro del presupuesto
- **WHEN** el conjunto está en ejecución y se mide la memoria residente de ambos contenedores
- **THEN** la suma es inferior a 400 MB

### Requirement: Parametrización del despliegue
La configuración específica de cada entorno (montaje del Data Lake, URL base de la
API externa, tiempo de espera) SHALL poder inyectarse en los contenedores por
variables de entorno, de modo que la misma imagen sirva para desarrollo y para el
entorno de destino sin reconstruir.

#### Scenario: Data Lake montado desde el host
- **WHEN** se define la variable de entorno que apunta al archivo del Data Lake y se levanta el conjunto
- **THEN** el contenedor del backend lee el archivo de la ruta indicada, sin necesidad de reconstruir la imagen

#### Scenario: Tiempo de espera de la API externa configurable
- **WHEN** se define la variable de entorno del tiempo de espera con un valor distinto del de por defecto
- **THEN** el backend aplica ese valor al llamar a Open-Meteo, sin recompilar el proyecto
