# Spec Delta

## Purpose

Data Lake sintético en CSV que aporta 730 días de historial de visitantes de Machu
Picchu, generado de forma determinista a partir de las reglas de negocio del sitio y
consultable en memoria por fecha, día de la semana, temporada y similitud climática.

## ADDED Requirements

### Requirement: Generación del Data Lake sintético
El sistema SHALL proveer un comando ejecutable que genere el archivo
`backend/datalake/machupicchu_history.csv` con exactamente 730 registros diarios, uno
por día consecutivos, y SHALL ser determinista: dos ejecuciones sobre el mismo código
deben producir un archivo byte-idéntico.

El rango de fechas SHALL partir de una época fija codificada en el generador (no de la
fecha de ejecución), de modo que el conjunto de datos no cambie según el día en que se
regenere. La aleatoriedad usada para dispersar los valores SHALL partir de una semilla
fija declarada en el código.

El generador SHALL aceptar como opciones la ruta de salida y la fecha de inicio, con
valores por defecto que apunten al archivo y a la época fijada, de modo que
`generar` sin argumentos produzca el Data Lake canónico.

#### Scenario: Ejecución por defecto produce el archivo canónico
- **WHEN** se ejecuta el generador sin argumentos
- **THEN** se crea `backend/datalake/machupicchu_history.csv` con 730 filas de datos más la fila de encabezado
- **AND** el rango de fechas del archivo es exactamente `[fecha_inicio, fecha_inicio + 729 días]`

#### Scenario: Regeneración reproducible
- **WHEN** se ejecuta el generador dos veces con la misma configuración
- **THEN** ambos archivos resultantes son idénticos byte a byte

#### Scenario: Rango personalizable
- **WHEN** se ejecuta el generador con una fecha de inicio distinta a la de por defecto
- **THEN** el archivo generado empieza en esa fecha y contiene 730 días consecutivos a partir de ella

### Requirement: Esquema del Data Lake
Cada fila del CSV SHALL tener exactamente las columnas, en este orden:
`fecha,dia_semana,temporada,clima,temperatura_c,es_fin_de_semana_o_feriado,visitantes_reales`.

- `fecha` SHALL estar en formato `YYYY-MM-DD`.
- `dia_semana` SHALL ser el nombre del día en español (`lunes`..`domingo`).
- `temporada` SHALL ser `seca` para los meses de mayo a octubre y `lluvias` para los meses de noviembre a abril.
- `clima` SHALL ser una de las cinco categorías del vocabulario fijo
  `despejado`, `nublado`, `lluvia`, `lluvia_torrencial`, `tormenta`.
- `temperatura_c` SHALL ser un número decimal de grados Celsius.
- `es_fin_de_semana_o_feriado` SHALL ser un valor booleano (`true`/`false`), y SHALL
  ser `true` cuando la fecha sea sábado, domingo o un feriado nacional peruano
  aplicable a la fecha de referencia.
- `visitantes_reales` SHALL ser un entero.

El archivo SHALL incluir una fila de encabezado y usar `,` como separador y `\n` como
fin de línea, de modo que pueda leerse con la biblioteca CSV estándar de Python sin
configuración adicional.

#### Scenario: Encabezado y columnas en el orden definido
- **WHEN** se lee la primera línea del CSV generado
- **THEN** es exactamente `fecha,dia_semana,temporada,clima,temperatura_c,es_fin_de_semana_o_feriado,visitantes_reales`

#### Scenario: Todas las filas tienen el mismo número de columnas
- **WHEN** se cuentan los campos de cada fila del CSV
- **THEN** todas las filas de datos contienen exactamente 7 campos

#### Scenario: Coherencia de la columna de fecha
- **WHEN** se recorren las fechas del CSV en orden
- **THEN** son consecutivas, sin huecos ni duplicados, y cada una es posterior en un día a la anterior

### Requirement: Reglas de negocio en los datos sintéticos
El generador SHALL aplicar las siguientes reglas al calcular `visitantes_reales`:

- La capacidad máxima oficial SHALL ser 5,600 visitantes por día, y ningún registro
  SHALL superar ese valor.
- En temporada seca (mayo-octubre) la afluencia base SHALL estar en el rango
  aproximado de 4,000 a 5,200 visitantes.
- En temporada de lluvias (noviembre-abril) la afluencia base SHALL estar en el
  rango aproximado de 1,800 a 3,200 visitantes.
- Las categorías de lluvia torrencial y tormenta SHALL reducir la afluencia respecto
  de la base de su temporada.
- Los días con `es_fin_de_semana_o_feriado` igual a `true` SHALL aumentar la
  afluencia aproximadamente un 15% respecto del mismo día tipo.
- `es_fin_de_semana_o_feriado` SHALL ser `true` para todo sábado y domingo, y para
  las fechas que coincidan con un feriado nacional peruano del catálogo del sistema,
  aunque el feriado caiga de lunes a viernes.
- `temperatura_c` SHALL ser coherente con la temporada: la temporada seca SHALL tener
  temperaturas más altas que la de lluvias, y los valores SHALL estar en un rango
  físicamente plausible para la zona (aproximadamente 5 °C a 28 °C).

#### Scenario: Ningún registro excede la aforo oficial
- **WHEN** se calcula el máximo de `visitantes_reales` sobre los 730 registros
- **THEN** el máximo es menor o igual que 5,600

#### Scenario: La temporada seca tiene mayor afluencia que la de lluvias
- **WHEN** se agrupan los registros por `temporada` y se compara la media de `visitantes_reales`
- **THEN** la media de `seca` es superior a la media de `lluvias` en al menos 1,000 visitantes

#### Scenario: Los rangos por temporada se cumplen
- **WHEN** se calculan los valores de `visitantes_reales` de los días que no son fin de semana ni feriado y no tienen lluvia torrencial ni tormenta
- **THEN** los días de temporada seca caen entre 4,000 y 5,200, y los días de temporada de lluvias caen entre 1,800 y 3,200

#### Scenario: El mal tiempo reduce la afluencia
- **WHEN** se compara la media de `visitantes_reales` de los días de lluvia torrencial o tormenta con la de su misma temporada y condición de fin de semana
- **THEN** la media de los días de mal tiempo es menor que la de los días sin mal tiempo

#### Scenario: El fin de semana y feriado marca correctamente los registros
- **WHEN** se filtran las filas con `es_fin_de_semana_o_feriado` igual a `true` y se las agrupa por `dia_semana`
- **THEN** el conjunto de días de la semana incluye `sábado` y `domingo`
- **AND** toda fecha que aparece en el catálogo de feriados nacionales peruanos presente en el rango está marcada con `true`, aunque su `dia_semana` sea de lunes a viernes
- **AND** toda fecha que no sea sábado, domingo ni feriado aparece con `false`

#### Scenario: Los feriados en día laborable elevan la afluencia
- **WHEN** se compara la media de `visitantes_reales` de los feriados que caen de lunes a viernes con la de los días laborables no feriado de su misma temporada y clima
- **THEN** la media de los feriados es mayor que la de los días laborables no feriado

### Requirement: Catálogo de feriados
El sistema SHALL mantener un catálogo fijo de feriados nacionales peruanos, con al
menos el Fiesta de la Independencia (28 de julio) e Inti Raymi (24 de junio), y
SHALL usarlo para marcar `es_fin_de_semana_o_feriado`. El catálogo SHALL ser un dato
declarado en el código, sin depender de una API externa de días festivos, para que la
generación del Data Lake sea determinista y funcione sin conexión.

#### Scenario: Los Holidays de referencia están en el catálogo
- **WHEN** se consulta el catálogo de feriados
- **THEN** contiene el 24 de junio y el 28 de julio

#### Scenario: El catálogo no requiere red
- **WHEN** el generador se ejecuta en un entorno sin acceso a Internet
- **THEN** el Data Lake se genera por completo, incluidos los marcados de feriado

### Requirement: Consulta del Data Lake en memoria
El sistema SHALL cargar el CSV una sola vez al iniciar el backend y SHALL mantenerlo
disponible en memoria para atender consultas sin releer el disco en cada petición.

El sistema SHALL permitir filtrar los registros por:

- conjunto de días de la semana (por ejemplo, sólo fines de semana, o sólo días
  laborables);
- conjunto de categorías climáticas;
- conjunto de temporadas;
- la condición `es_fin_de_semana_o_feriado` (verdadero o falso), que agrupa bajo una
  misma condición tanto a los fines de semana como a los feriados en día laborable;
- la fecha exacta, para recuperar el registro de un día concreto.

Un filtro sin resultados coincidentes SHALL devolver una colección vacía y SHALL NOT
provocar un error.

#### Scenario: Filtro por condición de fin de semana o feriado
- **WHEN** se solicitan los registros con `es_fin_de_semana_o_feriado` igual a `true`
- **THEN** todos los registros devueltos tienen ese valor, e incluyen tanto días de sábado y domingo como feriados que caen de lunes a viernes
- **AND** la media de `visitantes_reales` de ese conjunto es mayor que la del conjunto con el valor `false`

#### Scenario: Filtro por fecha exacta
- **WHEN** se solicita el registro de una fecha presente en el Data Lake
- **THEN** el sistema devuelve exactamente un registro, y el resultado está vacío si la fecha no está en el rango del Data Lake

#### Scenario: Filtro por conjunto de días de la semana
- **WHEN** se solicitan los registros de `sábado` y `domingo`
- **THEN** todos los registros devueltos tienen `dia_semana` en ese conjunto, y el número de resultados es menor que el total de registros

#### Scenario: Filtro por temporada
- **WHEN** se solicitan los registros de temporada `seca`
- **THEN** todos los registros devueltos tienen `temporada` igual a `seca`, y el número de resultados es menor que el total de registros

#### Scenario: Filtro sin coincidencias
- **WHEN** se solicita un filtro de días de la semana que no contiene ningún día, o una categoría climática inexistente
- **THEN** el sistema devuelve una colección vacía sin lanzar una excepción

#### Scenario: Carga única del archivo
- **WHEN** se atienden varias consultas consecutivas sobre el Data Lake
- **THEN** el archivo CSV se lee del disco una sola vez durante el ciclo de vida del proceso

### Requirement: Carga del archivo en ausencia de datos
Si el archivo CSV del Data Lake no existe o no puede leerse, el sistema SHALL fallar
al inicializar indicando explícitamente la ruta que no pudo cargar y SHALL indicar el
comando del generador como forma de resolverlo. El sistema SHALL NOT sustituir el
archivo por un conjunto de datos vacío ni inventar valores, porque produciría
estimaciones sin respaldo.

#### Scenario: Archivo ausente
- **WHEN** el backend se inicializa sin que exista el archivo CSV en la ruta configurada
- **THEN** la inicialización falla con un error que nombra la ruta del archivo y el comando del generador que produce el archivo

#### Scenario: Archivo malformado
- **WHEN** el backend se inicializa con un CSV cuyos encabezados no coinciden con el esquema esperado
- **THEN** la inicialización falla con un error que describe qué columna falta o sobra
