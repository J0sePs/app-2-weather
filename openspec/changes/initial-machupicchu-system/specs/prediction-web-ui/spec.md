# Spec Delta

## Purpose

Interfaz web de una sola página para que un turista consulte la previsión de
afluencia a Machu Picchu para el día de hoy o para cualquier fecha que elija, sin
necesidad de cuenta ni configuración previa.

## ADDED Requirements

### Requirement: Estructura de la página
La aplicación SHALL presentar una página con el encabezado
"Predicción de Afluencia - Machu Picchu", una barra de control con el selector de
fecha y el botón de consulta, y un área de resultado que se rellena tras la consulta.

La interfaz SHALL ser una SPA Angular con componentes standalone, sin renderizado en
servidor, y SHALL usar estilos CSS propios sin depender de una biblioteca de
componentes de terceros. El layout SHALL adaptarse a pantallas estrechas sin
desbordar horizontalmente.

#### Scenario: Contenido inicial de la página
- **WHEN** un usuario abre la aplicación
- **THEN** ve el encabezado "Predicción de Afluencia - Machu Picchu", un control de fecha, un botón "Consultar Afluencia" y el área de resultado vacía

#### Scenario: Sin contenido no solicitado
- **WHEN** un usuario abre la aplicación por primera vez
- **THEN** no ve resultados, mensajes de error ni indicadores de carga residuales de una consulta anterior

#### Scenario: Adaptabilidad a pantallas estrechas
- **WHEN** la ventana del navegador se reduce a 360 px de ancho
- **THEN** todo el contenido sigue siendo visible y accesible, sin scroll horizontal ni elementos superpuestos

### Requirement: Selector de fecha
La aplicación SHALL ofrecer un control de fecha nativo (`<input type="date">`) con
icono de calendario del navegador, y su valor SHALL estar inicializado a la fecha
actual en la zona horaria del sitio (`America/Lima`).

El valor por defecto SHALL ser la fecha de hoy en el momento de cargar la página, de
modo que el usuario pueda consultar la previsión sin interactuar con el control. El
control SHALL ser editable por el usuario.

#### Scenario: Fecha de hoy por omisión
- **WHEN** un usuario abre la aplicación sin tocar el control de fecha
- **THEN** el control de fecha muestra la fecha actual en `America/Lima` con el formato `YYYY-MM-DD`

#### Scenario: Selección de otra fecha
- **WHEN** un usuario elige una fecha distinta en el control
- **THEN** el valor del control se actualiza a esa fecha y queda disponible para la consulta

#### Scenario: Control de fecha nativo
- **WHEN** se inspecciona el control de fecha
- **THEN** es un elemento HTML nativo de tipo fecha, con su icono de calendario del navegador

### Requirement: Consulta de la previsión
Al pulsar el botón "Consultar Afluencia", la aplicación SHALL enviar una petición al
endpoint de predicción del backend usando la fecha del control como parámetro `date`
en formato `YYYY-MM-DD`, y SHALL enviar a la API la ruta esperada por el despliegue
con proxy, de modo que funcione tanto detrás de Nginx como en desarrollo.

Mientras la petición esté en curso, la aplicación SHALL mostrar un estado de carga y
SHALL deshabilitar el botón para evitar consultas duplicadas. Al completarse, el
estado de carga SHALL retirarse.

#### Scenario: Consulta correcta
- **WHEN** un usuario selecciona una fecha y pulsa "Consultar Afluencia"
- **THEN** la aplicación solicita la predicción para esa fecha y la muestra en la tarjeta de resultado
- **AND** el estado de carga desaparece al recibir la respuesta

#### Scenario: Sin consultas duplicadas
- **WHEN** una consulta está en curso
- **THEN** el botón de consulta está deshabilitado hasta que la consulta termine

#### Scenario: Envío del formato de fecha esperado por la API
- **WHEN** el usuario consulta con la fecha `2026-09-26` seleccionada
- **THEN** la petición enviada a la API incluye esa fecha en el parámetro `date` con el formato `YYYY-MM-DD`

### Requirement: Tarjeta de resultado
La tarjeta de resultado SHALL presentar, para la fecha consultada:

- el clima esperado: temperatura máxima en grados Celsius y condición atmosférica;
- los visitantes estimados, con separador de miles y el sufijo "personas";
- el porcentaje de aforo, con el texto que lo sitúa respecto del aforo permitido;
- una barra de capacidad visual que represente el porcentaje de aforo;
- una etiqueta de nivel de afluencia con el texto `Afluencia Alta`, `Afluencia
  Moderada` o `Afluencia Baja`, derivada de `crowd_level`;
- la fecha a la que corresponde el resultado.

La barra de capacidad SHALL tener un valor entre 0 y 100 y SHALL ser coherente con el
porcentaje mostrado como texto.

#### Scenario: Muestra de una previsión de afluencia alta
- **WHEN** la API devuelve 4,580 visitantes estimados, 81.8% de aforo y nivel `Alto` para `2026-09-26`
- **THEN** la tarjeta muestra la temperatura y la condición devueltas, "4,580 personas", el 81.8% del aforo permitido, la barra de capacidad al 81.8% y la etiqueta "Afluencia Alta"
- **AND** la tarjeta indica que el resultado corresponde al 2026-09-26

#### Scenario: Etiquetas según el nivel devuelto
- **WHEN** la API devuelve respectivamente `Bajo`, `Moderado` y `Alto`
- **THEN** la tarjeta muestra respectivamente "Afluencia Baja", "Afluencia Moderada" y "Afluencia Alta"

#### Scenario: Sustitución de una consulta anterior
- **WHEN** el usuario consulta una segunda fecha después de haber visto un resultado
- **THEN** la tarjeta muestra los valores de la segunda consulta, sin conservar cifras de la anterior

### Requirement: Aviso sobre el origen de los datos
La tarjeta de resultado SHALL incluir un aviso visible y permanente que indique que la
estimación se calcula sobre un historial sintético de demostración y que no
representa conteos oficiales de visitantes. El aviso SHALL mostrarse siempre que haya
una predicción en pantalla, y SHALL ser legible y estar distinguido tipográficamente
del resto de los datos numéricos para que no se confunda con un dato oficial.

#### Scenario: El aviso acompaña a toda predicción
- **WHEN** la tarjeta muestra una predicción para cualquier fecha
- **THEN** el aviso sobre el historial sintético está visible en la tarjeta

#### Scenario: El aviso no se confunde con el aforo
- **WHEN** se compara el texto del aviso con los datos numéricos de la tarjeta
- **THEN** el aviso se presenta como una nota destacada y no como un valor más de aforo o visitantes

### Requirement: Manejo de errores y estados vacíos
Si la API responde con error, la aplicación SHALL mostrar un mensaje legible derivado
del mensaje devuelto por la API, sinRenderizar una tarjeta de resultado, y SHALL
restablecer el botón de consulta a su estado utilizable.

Si la consulta no devuelve predicción, la aplicación SHALL informar de que no hay
previsión disponible para esa fecha en lugar de mostrar una tarjeta con valores
ausentes.

#### Scenario: Error de validación de la fecha
- **WHEN** la API responde con estado 422 y un mensaje sobre el rango de fechas admitido
- **THEN** la aplicación muestra ese mensaje al usuario y no muestra tarjeta de resultado
- **AND** el botón "Consultar Afluencia" vuelve a estar habilitado

#### Scenario: Servicio de clima no disponible
- **WHEN** la API responde con estado 502
- **THEN** la aplicación muestra un mensaje que indica que no se pudo obtener el pronóstico, sin detalle técnico de la respuesta

#### Scenario: Backend inaccesible
- **WHEN** la petición a la API no puede establecerse por un fallo de red
- **THEN** la aplicación muestra un mensaje que indica que el servicio no está disponible y rehabilita el botón de consulta

### Requirement: Base de pruebas del frontend
El proyecto SHALL contar con la infraestructura de pruebas unitarias del
esqueleto Angular generado (runner y configuración de test), de modo que los
componentes de la UI y el servicio de consulta puedan verificarse de forma aislada
simulando la API. Los casos de prueba del frontend SHALL cubrir, como mínimo, la
inicialización de la fecha, el formateo de la estimación y las etiquetas de nivel.

#### Scenario: El runner de pruebas ejecuta la suite
- **WHEN** se lanza el comando de pruebas del proyecto en un entorno sin navegador gráfico
- **THEN** la suite se ejecuta y devuelve un resultado de aprobado o suspenso sin requerir configuración adicional del desarrollador

#### Scenario: Formateo de la estimación verificado
- **WHEN** una prueba verifica el formato de 4,580 visitantes estimados
- **THEN** la cadena mostrada incluye el separador de miles y la palabra "personas"
