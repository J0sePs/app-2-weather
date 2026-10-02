# Spec Delta

## Purpose

Automatizar la verificación y la publicación de la aplicación de predicción de Machu
Picchu: comprobar en cada pull request que el backend y el frontend siguen cumpliendo
sus pruebas, y desplegar la rama `main` en la instancia EC2 por SSH sólo después de que
ambas comprobaciones pasan y de que un revisor lo aprueba.

## ADDED Requirements

### Requirement: Ejecución del pipeline ante cambios en la rama principal
El sistema SHALL ejecutar un único flujo de integración y despliegue definido en
`.github/workflows/ci-cd.yml`, disparado ante toda pull request dirigida a `main` y ante
todo `push` a `main`.

Ante una pull request, el flujo SHALL ejecutar únicamente los trabajos de verificación y
SHALL NOT intentar desplegar. Ante un `push` a `main`, el flujo SHALL ejecutar los
trabajos de verificación y, si todos terminan con éxito, el trabajo de despliegue.

El flujo SHALL NOT ejecutarse ante `push` a ninguna otra rama. El fallo de una
verificación en una pull request SHALL NOT impedir que la rama siga abierta a revisión,
y una ejecución del flujo SHALL NOT cancelar ni invalidar las ejecuciones concurrentes
de otra referencia.

#### Scenario: Una pull request dispara sólo las verificaciones
- **WHEN** se abre una pull request dirigida a `main` y se ejecuta el flujo
- **THEN** se ejecutan los trabajos de verificación del backend y del frontend y no se
  ejecuta ningún trabajo de despliegue

#### Scenario: Un push a main encadena verificación y despliegue
- **WHEN** se integran cambios en `main` y se ejecuta el flujo
- **THEN** se ejecutan los trabajos de verificación del backend y del frontend y, cuando
  ambos terminan con éxito, se ejecuta el trabajo de despliegue

#### Scenario: Los commits fuera de main no ejecutan el flujo
- **WHEN** se envía un `push` a una rama distinta de `main`
- **THEN** el flujo no se ejecuta

### Requirement: Verificación reproducible del backend
El sistema SHALL verificar el backend en un runner Linux sobre Python 3.12, instalando las
dependencias con el gestor de paquetes del proyecto y ejecutando la suite de pruebas
definida en su manifiesto.

La instalación SHALL NOT resolver versiones distintas de las fijadas en el archivo de
bloqueo del proyecto, de modo que la suite pase en el pipeline exactamente con las
versiones con las que se desarrolla y se despliega. El umbral de cobertura declarado en
el manifiesto SHALL formar parte de la verificación y SHALL causar el fallo del trabajo
cuando no se alcance.

Los trabajos de verificación SHALL NOT requerir credenciales de la nube que aloja la
instancia ni secretos del entorno de despliegue, para que una pull request abierta por
un tercero no alcance material sensible.

#### Scenario: La suite del backend se ejecuta con las versiones fijadas
- **WHEN** se ejecuta el trabajo de verificación del backend
- **THEN** las dependencias se instalan desde el archivo de bloqueo sin resolver versiones
  nuevas y la suite de pruebas se ejecuta completa

#### Scenario: Una prueba que falla o la cobertura es insuficiente detiene el pipeline
- **WHEN** alguna prueba del backend falla o la cobertura queda por debajo del umbral
  declarado en el manifiesto
- **THEN** el trabajo de verificación del backend termina con error y el trabajo de
  despliegue no llega a ejecutarse

#### Scenario: La verificación no exige credenciales de la nube
- **WHEN** se ejecuta el trabajo de verificación del backend sobre una pull request abierta
  por un tercero
- **THEN** la suite termina sin requerir credenciales de la nube que aloja la instancia ni
  secretos del entorno de despliegue

### Requirement: Verificación reproducible del frontend
El sistema SHALL verificar el frontend en un runner Linux con Node.js 20, instalando las
dependencias a partir del archivo de bloqueo del proyecto y ejecutando la suite de specs
de Angular de forma no interactiva y con un único intento de ejecución.

La ejecución SHALL NOT quedar en modo interactivo ni esperar entrada alguna del runner, y
SHALL usar un navegador sin interfaz gráfica. El proyecto SHALL exponer un comando de
verificación para integración continua distinguible del comando de pruebas de desarrollo
local, de modo que el pipeline no dependa de pasar banderas por línea de órdenes.

El runner SHALL disponer del navegador que usa el lanzador de pruebas del proyecto; el
flujo SHALL NOT depender de que ese navegador venga preinstalado en la imagen del runner.

#### Scenario: La suite del frontend se ejecuta de forma no interactiva
- **WHEN** se ejecuta el trabajo de verificación del frontend
- **THEN** el comando de verificación declarado por el proyecto se ejecuta con las
  dependencias instaladas desde el archivo de bloqueo y en un navegador sin interfaz
  gráfica, y el trabajo termina por sí solo al terminar la suite

#### Scenario: El comando de verificación está declarado en el proyecto
- **WHEN** se consulta el manifiesto del frontend
- **THEN** declara un comando de verificación para integración continua distinto del
  comando de pruebas de desarrollo, y ese comando no espera entrada por consola

#### Scenario: Una spec que falla detiene el pipeline
- **WHEN** alguna spec del frontend falla
- **THEN** el trabajo de verificación del frontend termina con error y el trabajo de
  despliegue no llega a ejecutarse

### Requirement: Despliegue condicionado a la rama principal y a las verificaciones
El sistema SHALL desplegar únicamente ante `push` a `main`, y SHALL ejecutarse después de
que tanto la verificación del backend como la del frontend hayan terminado con éxito. El
trabajo de despliegue SHALL NOT ejecutarse si alguna verificación falla o se cancela, y
en ese caso el flujo SHALL reportar el trabajo de despliegue como omitido por
dependencia, no como un error de despliegue.

#### Scenario: Un fallo de verificación impide el despliegue
- **WHEN** un `push` a `main` deja el trabajo de verificación del frontend en error
- **THEN** el trabajo de despliegue no se ejecuta y el flujo lo reporta como omitido

#### Scenario: Las verificaciones correctas habilitan el despliegue
- **WHEN** un `push` a `main` deja ambos trabajos de verificación con resultado correcto
- **THEN** el trabajo de despliegue se ejecuta

#### Scenario: Una pull request verde nunca despliega
- **WHEN** una pull request dirigida a `main` termina con sus verificaciones en correcto
- **THEN** no se ejecuta ningún trabajo de despliegue, aunque el flujo esté en verde

### Requirement: Aprobación humana antes de publicar
El trabajo de despliegue SHALL declarar el entorno `production` de GitHub, de modo que
GitHub aplique la protección del entorno antes de concederle acceso a sus secretos.

El entorno `production` SHALL tener activa una regla de revisores requeridos con un mínimo
de una persona, de modo que una ejecución de despliegue no pueda pasar sin que un
revisor la apruebe.

El fichero de workflow del repositorio SHALL NOT contener la clave privada, ningún token
de aprobación, ninguna credencial ni ninguna regla de protección embebida: la
configuración de la protección y de los secretos vive en el entorno de GitHub, no en el
repositorio.

#### Scenario: Un despliegue en verde queda a la espera de aprobación
- **WHEN** un `push` a `main` supera las verificaciones y el trabajo de despliegue declara
  el entorno `production`
- **THEN** el trabajo queda pendiente de revisión y no ejecuta el script de publicación
  hasta que un revisor lo aprueba

#### Scenario: La publicación ocurre tras la aprobación
- **WHEN** un revisor requerido aprueba la ejecución en espera
- **THEN** el trabajo de despliegue se reanuda y ejecuta el script de publicación

#### Scenario: El repositorio no declara secretos ni reglas de protección
- **WHEN** se inspecciona el fichero de workflow del repositorio
- **THEN** no contiene ninguna clave privada, ningún token, ningún valor literal de
  conexión al servidor ni ninguna regla de protección de entorno

### Requirement: Publicación por SSH sobre la configuración versionada
El sistema SHALL publicar la aplicación ejecutando, de forma remota y sobre la instancia
que aloja el servicio, una secuencia de pasos que termine con el conjunto de contenedores
definido en el repositorio levantado y en ejecución.

El script de publicación SHALL habilitar al principio el modo de detenerse ante el primer
error, de modo que un fallo intermedio no continúe hasta un paso cuyo resultado dependa de
él. La secuencia SHALL consistir en, en este orden:

1. Posicionarse en el directorio del repositorio, dentro del directorio personal del
   usuario de conexión.
2. Actualizar ese repositorio desde la rama `main`.
3. Posicionarse en el directorio de infraestructura de ese repositorio.
4. Levantar y reconstruir los servicios con Docker Compose.
5. Eliminar las imágenes de contenedor sin referencias.

El paso de actualizar el repositorio SHALL NOT ejecutarse como `root`, porque un
directorio propiedad de `root` impediría las actualizaciones posteriores. El sistema
SHALL NOT construir las imágenes fuera de la instancia, ni publicar un registro de
imágenes, ni ejecutar el motor de contenedores mediante un mecanismo de elevación de
privilegios, porque la instancia ya tiene preparado tanto el permiso de usuario como el
espacio de intercambio que la publicación necesita.

#### Scenario: La publicación deja la versión nueva en servicio
- **WHEN** se aprueba y se ejecuta el trabajo de despliegue
- **THEN** el repositorio de la instancia queda actualizado a la revisión integrada en
  `main` y los servicios se reconstruyen y quedan en ejecución

#### Scenario: Un fallo intermedio detiene la publicación
- **WHEN** alguno de los pasos de la secuencia del script devuelve un código de salida
  distinto de cero
- **THEN** el script se detiene en ese paso y no ejecuta los pasos posteriores

#### Scenario: La publicación no deja imágenes huérfanas
- **WHEN** la publicación termina con éxito
- **THEN** las imágenes de contenedor sin referencias se han eliminado de la instancia

#### Scenario: La publicación no requiere elevación de privilegios
- **WHEN** se inspecciona el contenido del script de publicación
- **THEN** ninguno de sus comandos invoca el motor de contenedores mediante un mecanismo
  de elevación de privilegios, ni actualiza el repositorio como `root`

### Requirement: Secretos de conexión por entorno, no versionados
El trabajo de despliegue SHALL obtener el host, el usuario y la clave privada de conexión
a la instancia de los secretos del entorno `production`, y SHALL NOT esperar que se
declaren a nivel de repositorio.

El entorno `production` SHALL secretar, como mínimo, la dirección del host, el nombre de
usuario de conexión y el contenido íntegro de la clave privada de despliegue. La dirección
del host SHALL ser la que publica la salida de dirección pública de la instancia del
módulo de infraestructura, de modo que exista una única fuente para ese valor.

El pipeline SHALL NOT requerir ninguna credencial adicional distinta de las tres
anteriores, y en particular SHALL NOT requerir credenciales de la nube que aloja la
instancia. Los secretos SHALL NOT quedar registrados en la salida de la ejecución.

#### Scenario: El despliegue se autentica con los secretos del entorno
- **WHEN** el trabajo de despliegue se ejecuta tras la aprobación
- **THEN** se conecta a la instancia usando la dirección, el usuario y la clave privada
  tomados de los secretos del entorno, sin pedir ninguna credencial adicional

#### Scenario: La dirección del host tiene una única fuente
- **WHEN** se configura el secreto de dirección del host con la salida de dirección
  pública de la instancia
- **THEN** el trabajo de despliegue alcanza la instancia que aloja la aplicación sin
  dirección escrita a mano en el repositorio

#### Scenario: Los secretos no se exponen en la salida
- **WHEN** se revisa el registro completo de una ejecución del trabajo de despliegue
- **THEN** no aparece el material de la clave privada ni el valor del host

### Requirement: Versiones de las acciones fijadas
El flujo de trabajo SHALL invocar cada acción de terceros por una referencia de versión
explícita, una etiqueta numerada o un identificador de commit, y SHALL NOT invocar
ninguna por una referencia móvil ni por una versión mayor sin fijar, porque una etiqueta
móvil puede cambiar de contenido entre dos ejecuciones sin que el repositorio registre
ese cambio.

#### Scenario: Todas las acciones están fijadas
- **WHEN** se inspecciona el fichero de workflow y se listan las acciones que invoca
- **THEN** cada una declara una versión explícita y ninguna se referencia por una rama ni
  por una etiqueta móvil

#### Scenario: El workflow es válido para GitHub Actions
- **WHEN** se valida el fichero de workflow con la sintaxis del formato de Actions
- **THEN** la validación no reporta errores de estructura