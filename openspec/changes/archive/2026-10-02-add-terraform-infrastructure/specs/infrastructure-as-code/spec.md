# Spec Delta

## Purpose

Provisionar en AWS, de forma declarativa y reproducible, el host público que aloja la
aplicación de predicción de Machu Picchu —red, reglas de acceso, par de claves e
instancia EC2 con su arranque automático— de modo que toda la infraestructura se cree y
se destruya desde el repositorio, sin pasos manuales en la consola de AWS.

## ADDED Requirements

### Requirement: Módulo Terraform de un solo comando
El sistema SHALL proveer la definición completa de la infraestructura AWS en el módulo
Terraform de `infra/terraform/`, compuesto por `main.tf` con el provider y los recursos,
`variables.tf` con las entradas, `outputs.tf` con las salidas, `user_data.sh` con el
guión de arranque y `terraform.tfvars.example` con un ejemplo de configuración.

Desde una copia limpia del módulo, una única ejecución de `terraform apply` SHALL crear
la red, el grupo de seguridad, el par de claves y la instancia, sin ninguna otra
operación manual. Una segunda ejecución de `terraform apply` sobre la misma
configuración SHALL informar de cero cambios, porque el estado debe describir la
infraestructura real.

La configuración SHALL estar formateada con `terraform fmt` y SHALL validar con
`terraform validate` sin advertencias ni errores.

#### Scenario: La infraestructura completa se crea desde cero
- **WHEN** se ejecuta `terraform init` y después `terraform apply` sobre un módulo sin
  estado previo en una cuenta limpia
- **THEN** la ejecución termina con éxito y quedan creados el VPC, el gateway de
  Internet, la subnet pública, la tabla de rutas, el grupo de seguridad, el par de
  claves y la instancia EC2

#### Scenario: La aplicación es idempotente
- **WHEN** se ejecuta `terraform apply` por segunda vez sin modificar la configuración
- **THEN** la ejecución informa de que no hay cambios que aplicar y no crea ni destruye
  ningún recurso

#### Scenario: El módulo es estáticamente válido y formateado
- **WHEN** se ejecutan `terraform validate` y `terraform fmt -check`
- **THEN** ambos terminan con código de salida 0 y sin informe de cambios de formato

### Requirement: Red pública con salida a Internet
El sistema SHALL definir una VPC con el bloque CIDR `10.0.0.0/16`, con el soporte de
nombres de host DNS habilitado, para que las instancias extiendan resolución de nombres sin
depender de un servicio externo.

La VPC SHALL estar conectada a Internet mediante un gateway de Internet asociado. Dentro
de la VPC SHALL existir una subnet pública con el bloque CIDR `10.0.1.0/24` que asigne
dirección IP pública a cada instancia que se lance en ella, y que reciba una tabla de
rutas con una ruta por defecto que envíe todo el tráfico no emparejado al gateway de
Internet.

#### Scenario: La instancia alcanza Internet
- **WHEN** se consulta desde la instancia EC2 un nombre público de un servicio externo
- **THEN** la resolución y la conexión se completan sin necesidad de NAT Gateway ni de
  gateway de salida

#### Scenario: El tráfico de la subnet sale a Internet
- **WHEN** se inspecciona la tabla de rutas asociada a la subnet pública
- **THEN** existe una ruta con destino `0.0.0.0/0` que apunta al gateway de Internet de
  la VPC

### Requirement: Grupo de seguridad de superficie mínima
El sistema SHALL definir un grupo de seguridad que permita tráfico de entrada por TCP en
el puerto 22 únicamente desde el prefijo CIDR de 32 bits formado por `my_ip`, y por TCP en
el puerto 80 desde cualquier dirección. El grupo SHALL permitir tráfico de salida sin
restricción, y SHALL NOT permitir ninguna otra regla de entrada.

El puerto 22 SHALL NOT quedar accesible desde `0.0.0.0/0` en ninguna circunstancia del
despliegue por omisión, para que la instancia no quede expuesta a escaneo de puerto
abierto desde Internet.

#### Scenario: SSH restringido a la IP del operador
- **WHEN** se describe el grupo de seguridad tras el despliegue y se consulta su regla de
  entrada para el puerto 22
- **THEN** el único origen permitido es el prefijo `/32` que corresponde a `my_ip` y no
  incluye ninguna otra red

#### Scenario: La aplicación es accesible desde Internet
- **WHEN** un navegador cualquiera solicita por HTTP el puerto 80 de la dirección IP
  pública de la instancia
- **THEN** la conexión alcanza el servidor web de la aplicación

#### Scenario: No hay reglas de entrada adicionales
- **WHEN** se inspecciona el conjunto completo de reglas de entrada del grupo de seguridad
- **THEN** sólo existen las dos reglas de puerto 22 y puerto 80 descritas, sin reglas
  para otros puertos ni rangos abiertos a `0.0.0.0/0`

### Requirement: Acceso por SSH con un par de claves externo
El sistema SHALL registrar en AWS un par de claves con el nombre `app2w-deploy`, tomando
la clave pública del archivo indicado por la variable `public_key_path`, cuyo valor por
omisión es `~/.ssh/app2w-deploy.pub`. La ruta SHALL resolverse admitiendo el prefijo `~`
de directorio personal.

El material privado de autenticación SHALL NOT gestionarse como recurso de Terraform: la
clave privada SHALL NOT guardarse en el estado, SHALL NOT versionarse en el repositorio
y SHALL existir únicamente en la máquina del operador y, cuando proceda, como secreto del
pipeline.

#### Scenario: La clave registrada corresponde al par del operador
- **WHEN** se aplica el módulo y después se describe el par de claves en AWS
- **THEN** existe con el nombre `app2w-deploy` y su material público coincide con el del
  archivo local indicado por `public_key_path`

#### Scenario: La ruta con `~` se resuelve
- **WHEN** se aplica el módulo con el valor por omisión de `public_key_path` y el archivo
  existe en el directorio personal del operador
- **THEN** la clave pública se lee sin error y la aplicación se completa

#### Scenario: La clave privada no está en el estado
- **WHEN** se inspecciona el archivo de estado o el plan de la configuración completa
- **THEN** no aparece ninguna clave privada ni ningún secreto de autenticación de la
  instancia

### Requirement: Instancia EC2 dimensionada al presupuesto de memoria
El sistema SHALL crear una instancia EC2 del tipo `t3.micro`, la más pequeña cubierta por
el nivel de Instance Free Tier, con un volumen raíz de 8 GB de tipo `gp3`.

La AMI SHALL resolverse en tiempo de plan mediante el catálogo de AMI de AWS, restringido
al propietario `amazon` y al patrón de nombre de Amazon Linux 2023 para arquitectura
`x86_64`, seleccionando la imagen más reciente que coincida. El patrón SHALL corresponde a
la imagen base de Amazon Linux 2023 y SHALL NOT capturar las variantes especializadas que
Amazon publica bajo el mismo prefijo (imágenes *minimal* y optimizadas para ECS o para el
acelerador Neuron), porque no son la imagen que espera el arranque.

La referencia a la AMI SHALL ser por dato y no por identificador escrito a mano, de modo
que una publicación nueva de Amazon se incorpore declarando el reemplazo de la instancia
en el plan, en lugar de requerir que alguien busque y pegue un `ami_id`.

La instancia SHALL recibir una dirección IP pública al lanzarse y SHALL ser accesible por
la dirección pública de su subred, sin depender de una Elastic IP gestionada aparte.

#### Scenario: La instancia se lanza con la imagen esperada
- **WHEN** se consulta el plan y después se describe la instancia creada
- **THEN** su tipo es `t3.micro`, su imagen corresponde a Amazon Linux 2023 y su volumen
  raíz tiene 8 GB de tipo `gp3`

#### Scenario: La resolución de la AMI es inequívoca
- **WHEN** se ejecuta `terraform plan` sin haber fijado el identificador de la AMI
- **THEN** la consulta al catálogo de AMI devuelve una única imagen de Amazon Linux 2023
  base para `x86_64`, sin exigir un identificador escrito a mano y sin elegir una
  variante *minimal*, de ECS o de Neuron

#### Scenario: La AMI resuelta es la imagen base
- **WHEN** se describe por su nombre la imagen que el plan resolvió
- **THEN** el nombre corresponde a Amazon Linux 2023 con arquitectura `x86_64` y no
  contiene los sufijos de variante `minimal`, `ecs-hvm` ni `ecs-neuron-hvm`

#### Scenario: La instancia tiene dirección pública
- **WHEN** se describe la instancia y se consulta la dirección pública de su subred
- **THEN** tiene una dirección IPv4 pública asignada

### Requirement: Arranque automático e idempotente de la instancia
El sistema SHALL adjuntar a la instancia un script de arranque que, en el primer
arranque, deje el host preparado para alojar y desplegar la aplicación sin intervención
manual. El script SHALL:

1. Actualizar el sistema e instalar el motor de contenedores y el cliente de Git.
2. Habilitar e iniciar el servicio de contenedores y conceder al usuario de la
   instancia permiso para usarlo sin privilegios de root.
3. Instalar el complemento de línea de comandos de Docker Compose versión 2 en el
   directorio de complementos reconocido por el motor de contenedores.
4. Crear un archivo de intercambio de 2 GB, activarlo y persistirlo en la tabla de
   montajes del sistema.
5. Clonar el repositorio de la aplicación en el directorio personal del usuario de la
   instancia, ejecutado como ese usuario y no como root.
6. Marcar el final del arranque creando un archivo de marca.

El script SHALL ser idempotente: su ejecución repetida SHALL NOT fallar ni dejar el host
en un estado inconsistente. El sistema SHALL NOT dejar ninguna de las credenciales de
acceso al repositorio escritas en el sistema de archivos de la instancia.

#### Scenario: El host queda preparado para desplegar
- **WHEN** la instancia termina su primer arranque y se marca el final del script
- **THEN** el motor de contenedores está habilitado y en ejecución, el usuario de la
  instancia puede usarlo sin `sudo`, el complemento de Docker Compose versión 2 responde
  a su versión, hay un archivo de intercambio de 2 GB activo y el repositorio de la
  aplicación está clonado en el directorio personal del usuario

#### Scenario: El intercambio persiste tras reiniciar
- **WHEN** se reinicia la instancia y se consulta el espacio de intercambio en uso
- **THEN** sigue activa la misma unidad de intercambio de 2 GB, porque está declarada en
  la tabla de montajes del sistema

#### Scenario: El arranque se puede repetir sin fallar
- **WHEN** se ejecuta de nuevo el script de arranque sobre el mismo host
- **THEN** termina sin error y el host conserva el motor de contenedores, el
  complemento, el intercambio y el repositorio ya preparado

#### Scenario: El despliegue de la aplicación es posible tras el arranque
- **WHEN** se conectan Docker Compose y el repositorio clonado mediante la variable de
  entorno de grupo del usuario de la instancia
- **THEN** la aplicación se levanta sin necesidad de escribir en la configuración del
  servicio de contenedores

### Requirement: Parametrización del despliegue
El sistema SHALL exponer como variables de entrada la región de AWS, con valor por
omisión `us-east-1`; el prefijo CIDR de la IP del operador, sin valor por omisión; la ruta
del archivo de clave pública, con valor por omisión `~/.ssh/app2w-deploy.pub`; y el
nombre del proyecto, con valor por omisión `app-2-weather`.

La variable de la IP del operador SHALL NOT tener valor por omisión, de modo que el
despliegue falle de forma explícita en lugar de abrir el acceso por SSH a un rango
elegido por omisión que nadie ha revisado. El módulo SHALL proveer un archivo de ejemplo
`terraform.tfvars.example` que documente todas las variables con valores de muestra
sustituibles.

La región declarada SHALL aplicarse a todos los recursos y al provider, de modo que
cambiar `aws_region` permita crear un entorno equivalente en otra región.

#### Scenario: El despliegue exige declarar la IP del operador
- **WHEN** se ejecuta `terraform plan` sin declarar `my_ip`
- **THEN** el comando falla pidiendo ese valor, sin llegar a crear ni planificar
  recursos con un origen de SSH inventado

#### Scenario: El ejemplo documenta las variables
- **WHEN** se lee `terraform.tfvars.example`
- **THEN** contiene una entrada para cada variable del módulo, con la clave pública de
  ejemplo y la IP de operador de ejemplo

#### Scenario: Cambiar de región traslada la infraestructura
- **WHEN** se declara `aws_region` con una región distinta de la del omisión y se aplica
- **THEN** todos los recursos creados pertenecen a esa región

### Requirement: Salidas utilizables desde el despliegue
El sistema SHALL exponer como salidas la dirección IP pública de la instancia, su nombre
de DNS público, y el comando completo de conexión SSH construido con el nombre de la clave
registrada y el usuario de la instancia, listo para copiar y pegar.

La dirección IP pública SHALL estar disponible como salida porque es el valor que el
pipeline de despliegue consume como secreto de host. El comando de conexión SHALL
referenciar el archivo de clave privada local en la ruta esperada por el pipeline.

#### Scenario: El pipeline obtiene el host
- **WHEN** se consultan las salidas tras aplicar el módulo
- **THEN** la salida de dirección IP pública contiene la IPv4 de la instancia y es
  apta para asignarse al secreto de host del entorno de despliegue

#### Scenario: El comando de conexión es utilizable sin editarlo
- **WHEN** se lee la salida del comando de conexión y se ejecuta en una máquina que
  tiene la clave privada local
- **THEN** abre una sesión en la instancia sin que haya que corregir usuario, clave ni
  dirección

### Requirement: Etiquetado uniforme de los recursos
Todos los recursos creados por el módulo SHALL llevar un nombre con el prefijo `app2w-`
seguido de su función, y las etiquetas `Project` con el valor de la variable
`project_name` y `ManagedBy` con el valor `terraform`.

El etiquetado SHALL cubrir todos los recursos cuyo esquema de la API lo soporte. La
relación entre la tabla de rutas y la subnet SHALL NOT exigir etiquetas propias porque su
esquema no las admite, y SHALL seguir siendo localizable a través de la subnet y la tabla
de rutas, que sí las llevan. El inventario por etiqueta SHALL permitir distinguir los
recursos del proyecto de los que no gestiona Terraform.

#### Scenario: Los recursos son identificables
- **WHEN** se consultan los recursos del proyecto en la cuenta por etiqueta
- **THEN** los recursos que admiten etiquetas aparecen con `ManagedBy` igual a
  `terraform`, `Project` igual al valor de `project_name` y un `Name` con el prefijo
  `app2w-`

#### Scenario: La relación entre tabla de rutas y subnet es localizable
- **WHEN** se busca la subnet del proyecto por la etiqueta `Project`
- **THEN** la subnet y su tabla de rutas aparecen etiquetadas, y con ellas se llega a la
  asociación que las une aunque esa asociación no admita etiquetas por esquema

#### Scenario: El nombre del proyecto es configurable
- **WHEN** se declara `project_name` con un valor distinto del de omisión y se aplica
- **THEN** la etiqueta `Project` de los recursos toma ese valor

### Requirement: Estado y secretos fuera del control de versiones
El módulo SHALL incluir un archivo `.gitignore` que excluya el directorio de plugins y
caché de Terraform, todos los archivos de estado —incluidos los de copia de seguridad y
los de plan—, los logs de fallo del proveedor, los archivos de variables reales y los
overrides locales. El estado contiene la dirección pública de la instancia y el prefijo
CIDR del operador, por lo que SHALL NOT quedar en el historial del repositorio.

Los archivos que sí son necesarios para reconstruir la infraestructura —la definición, el
guión de arranque, el ejemplo de variables y el archivo de bloqueo del proveedor—
SHALL permanecer versionados. El archivo de bloqueo SHALL NOT excluirse: no contiene
credenciales, sólo la versión del provider y sus sumas de verificación, y versionarlo es
lo que garantiza que un `terraform init` posterior resuelva el mismo provider.

#### Scenario: El estado no se versiona
- **WHEN** se consulta el estado del repositorio tras inicializar y aplicar el módulo
- **THEN** no aparecen como modificados ni como pendientes de añadir el directorio de
  caché, los archivos de estado ni el archivo de variables reales

#### Scenario: La definición sí se versiona
- **WHEN** se consulta el estado del repositorio tras crear el módulo e inicializarlo
- **THEN** los archivos de definición, el script de arranque, el ejemplo de variables y
  el archivo de bloqueo del provider aparecen como archivos nuevos listos para confirmar

#### Scenario: El bloqueo del provider se conserva
- **WHEN** se consulta qué ficheros del módulo quedan bajo control de versiones
- **THEN** el archivo de bloqueo del provider está incluido, porque fija la versión del
  provider y sus sumas de verificación sin contener secretos

#### Scenario: El estado no contiene credenciales de acceso
- **WHEN** se inspecciona el archivo de estado generado
- **THEN** contiene identificadores y direcciones de los recursos y el material público
  del par de claves, pero ninguna clave privada ni token de acceso a AWS