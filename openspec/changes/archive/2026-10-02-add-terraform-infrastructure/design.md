# Design

## Context

Ver `proposal.md` para la motivación. El estado actual relevante para el diseño es
este:

- La aplicación está completa y verificada: backend FastAPI, frontend Angular, ambas
  imágenes Docker y `infra/docker-compose.yml` (capacidad `containerized-deployment`).
- `openspec/project.md` prescribe en prosa la infraestructura objetivo. Este change
  convierte esa prosa en código sin reinterpretarla: los valores que fija el contrato
  (CIDRs, `t3.micro`, 8 GB `gp3`, prefijo `app2w-`, `my_ip/32` para SSH) son
  requirements del contrato, no preferencias de diseño, y este documento no los
  contradice.
- `infra/` contiene hoy un único archivo (`docker-compose.yml`) y
  `infra/.dockerignore`. No hay Terraform en el repositorio, ni convención heredada de
  IaC, ni variables de entorno de AWS fijadas.
- Terraform v1.14.5 está instalado en la máquina de desarrollo, así que
  `terraform validate` y `terraform fmt -check` son ejecutables localmente como
  verificación.
- La clave `~/.ssh/weather-deploy` existe en esta máquina; el contrato y este change
  usan `app2w-deploy`, que hay que generar.
- El presupuesto de memoria (< 400 MB de runtime, instancia de 1 GB) es la razón por la
  que el arranque necesita swap: el build de las imágenes Docker es lo que se queda sin
  memoria, no el runtime.
- El workflow de GitHub Actions que consumirá `instance_public_ip` es una sección
  distinta del contrato y no forma parte de este change; el diseño sólo deja el output
  listo para eso.

Restricciones que condicionan las decisiones:

- Los artefactos (specs, código, comentarios) se escriben en español, siguiendo el idioma
  del contrato y de los specs ya archivados.
- El estado de Terraform se mantiene local: el diseño no puede depender de que exista un
  bucket S3 configurado en la cuenta del operador.

## Goals / Non-Goals

**Goals:**

- Un `terraform apply` desde una copia limpia del módulo que cree toda la
  infraestructura, y un `terraform destroy` que la elimine completa sin residuos.
- Configuración verificable sin tocar AWS: `terraform fmt -check` y `terraform validate`
  deben pasar en local y ser parte de la verificación del cambio.
- Que el estado y los secretos del operador no puedan llegar a un commit por descuido.
- Que el host quede preparado para que el despliegue de la aplicación sea un
  `docker compose up -d --build` sin pasos manuales adicionales.
- Que los outputs sean directamente consumibles por el pipeline futuro, sin parsing.

**Non-Goals:**

- Alta disponibilidad, escalado automático o varias zonas de disponibilidad. Una
  instancia es el objetivo (ver `proposal.md`).
- Cualquier recurso que la aplicación no use en runtime: IAM roles, RDS, balanceador,
  Route 53, NAT Gateway. Ver la sección de non-goals del contrato.
- Backend remoto de estado (S3 + DynamoDB), locking, versionado del estado y
 separación por entorno/workspace.
- Provisionar el pipeline de GitHub Actions. Este change sólo produce el output que el
  pipeline consumirá.
- Variables de CloudWatch, Instance Scheduler ni alertas de coste.
- Optimizar el precio con Savings Plans, instancias reservadas o selección de AZ por
  latencia.

## Decisions

### 1. Un solo directorio `infra/terraform/`, sin backend remoto y sin módulos anidados

Todo el módulo vive en `infra/terraform/` como un único directorio raíz, sin
`provider` por entorno, sin submódulos ni `required_providers` de terceros. El backend es
el implícito local (`terraform.tfstate`).

Racional: es el layout que el contrato fija y el que hace que `cd infra/terraform &&
terraform apply` funcione sin más. El estado local es aceptable porque hay una sola
persona desplegando y una sola instancia: el estado describe una infraestructura de
proyecto trivial de reconstruir si se pierde, y `proposal.md` ya lo declara non-goal.
La alternativa (S3 + DynamoDB) aporta concurrencia segura entre operadores, que es un
problema que este proyecto no tiene.

Consecuencia asumida: el estado no se comparte ni se protege con control de acceso, así
que la mitigación es ignorarlo en git (decisión 8), no distribuirlo.

### 2. `my_ip` sin valor por omisión, y `public_key_path` con `pathexpand`

`my_ip` se declara sin `default`, con `validation` que comprueba que sea un prefijo CIDR
de host y termina en `/32`, y con una descripción que muestra el comando para obtenerlo.
La clave pública se lee con `file(pathexpand(var.public_key_path))`.

Racional: Terraform no expande `~` en `file()`. Si el valor por omisión fuera
`~/.ssh/app2w-deploy.pub` y se leyera con `file()` a secas, el apply fallaría con un error
de fichero no encontrado en una ruta literal con tilde, que es un diagnóstico confuso.
`pathexpand` (disponible desde Terraform 1.3; aquí hay 1.14.5) hace que el valor por
omisión documentado en el contrato funcione de verdad. La `validation` convierte un error
de conexión en un mensaje que dice qué hacer.

El prefijo `/32` se impone por validación en lugar de por concatenación en `main.tf` para
que un error de dedo en el `.tfvars` (`1.2.3.4/24` en vez de `1.2.3.4/32`) falle al
validar en vez de abrir SSH a una red entera.

Alternativa descartada: valor por omisión `0.0.0.0/0` con la instrucción de ajustarlo en
un comentario. Se descartó porque el fallo es silencioso por definición: nadie revisa un
comentario antes de exponer SSH a Internet, y el error se descubre cuando ya hubo
escaneo.

### 3. AMI resuelta por `data "aws_ami"` con `name_regex` estricto y `most_recent = true`

La AMI se resuelve con `owners = ["amazon"]`,
`name_regex = "^al2023-ami-[0-9][0-9.]*-kernel-[0-9][0-9.]*-x86_64$"` y
`most_recent = true`, y se referencia por `data.aws_ami.al2023.id`.

Racional: sin `most_recent = true`, la consulta devuelve varias coincidencias y Terraform
falla con "your query returned more than one result", que convierte un despliegue de un
comando en un paso manual. El patrón no captura las variantes ARM porque terminan en
`-arm64`. Filtrar por `owners = ["amazon"]` evita que una AMI de un tercero con nombre
parecido sea candidata.

Dos ajustes fueron necesarios tras verificar el plan contra la API real, y ambos son la
razón de que el patrón sea estricto:

- **El argumento cambió de nombre.** En el provider v6, `name_pattern` ya no existe: se
  llama `name_regex` y recibe una expresión regular en lugar de un glob. Mantener el
  nombre del contrato con `~> 5.0` era la otra opción y se descartó: fija el módulo a un
  provider ya superado para conservar el nombre de un argumento, no por alguna capacidad
  que aportara.
- **Un glob flojo selecciona la variante equivocada.** `al2023-ami-*-x86_64` también
  captura las variantes que Amazon publica bajo el mismo prefijo (`minimal`, `ecs-hvm`,
  `ecs-neuron-hvm`). Como `most_recent` ordena por fecha de creación y la variante
  optimizada para el acelerador AWS Neuron se publica con fecha posterior, el plan
  arrancaba la instancia con `al2023-ami-ecs-neuron-hvm-...` en lugar de la imagen
  base. Exigir una versión numérica detrás de `al2023-ami-` y de `kernel-` deja fuera
  todas las variantes; así se resolvió `al2023-ami-2023.12.20260930.0-kernel-6.1-x86_64`.

Coste aceptado: la AMI no está fijada, así que una actualización del AL2023 aparece como
un cambio de plan que pide destruir y recrear la instancia (no un arranque in-place). Es
un coste aceptable y desirable para una instancia desechable: fija el `ami_id` sólo para
obtener reproducibilidad exacta si alguna vez hiciera falta, no por omisión.

Detalle conocido: Amazon publica una imagen por versión de kernel (6.1, 6.12, 6.18...)
con la misma fecha de creación, así que `most_recent` desempata entre ellas como pueda.
Todas son la misma AL2023 y cualquiera sirve, pero si el desempate cambia el `ami_id`
cambia y el plan pedirá recrear la instancia; es el mismo trade-off ya asumido.

### 4. `user_data.sh` como archivo aparte, leído con `file()`, no plantilla

El arranque se mantiene en `infra/terraform/user_data.sh` y la instancia lo carga con
`user_data_base64 = base64encode(file("${path.module}/user_data.sh"))`.

Racional: un script de arranque de ~30 líneas en HCL con heredocs es ilegible y
difícil de revisar; como archivo se puede leer, editar con cualquier editor y correr
localmente con `shellcheck` o `bash -n`. `${path.module}` en vez de `"user_data.sh"` a
secas porque la ruta relativa de `file()` es relativa al directorio de trabajo actual, no
al del módulo: con `terraform -chdir` o desde otro directorio, la versión corta se rompe
con un error que no menciona el directorio esperado.

Se codifica en base64 porque el provider v6 advierte si `user_data` se deja en claro, y el
requisito de validación es que `terraform validate` pase sin advertencias. Con
`user_data_base64` el estado guarda la forma base64 en lugar del texto plano. El script no
contiene secretos —instala paquetes y clona un repositorio público—, así que la
codificación responde a la advertencia del provider, no a una amenaza concreta.

El `git clone` va URL literal del repositorio público porque es fijo y no es un secreto,
lo que evita tener que pasar la URL por variable de entorno o `templatefile` sin ganar
nada.

### 5. El arranque instala Docker desde el repositorio de Docker, no desde el paquete de AL2023

El script ejecuta `dnf update -y`, instala `git`, y añade el repositorio oficial
`docker-ce` para instalar `docker-ce` y `docker-ce-cli`; el complemento
`docker-compose-plugin` se descarga como binario a releases de Docker y se instala en
`/usr/local/lib/docker/cli-plugins/docker-compose`, con `chmod +x`.

Racional: el paquete `docker` de Amazon Linux 2023 no incluye el complemento de Compose
v2, y `docker compose up --build` (el comando que usa el despliegue documentado en el
contrato) falla sin él. Instalar el paquete de Amazon deja además la instalación en un
directorio del sistema que no es el que el motor busca, lo que produce un fallo confuso.
Bajar el binario oficial a la ruta de complementos reconocida, con `chmod +x` explícito
porque el binario no lo trae tras descomprimir, hace que `docker compose version`
responda en la misma máquina donde `docker` responde.

Alternativa descartada: copiar el plugin con `docker cp` desde la AMI de referencia, que
es el truco que improvisan muchos scripts. Se descartó porque requiere una AMI de
referencia que mantener y falla en silencio cuando la versión del plugin queda
desfasada respecto al motor.

### 6. Swap de 2 GB creado y persistido, y `ec2-user` en el grupo `docker`

El script crea `/swapfile` con `fallocate`, le asigna permisos `600`, ejecuta
`mkswap`, `swapon`, añade una línea idempotente a `/etc/fstab`, y sólo entonces añade
`ec2-user` al grupo `docker`. El clon del repositorio se ejecuta con `su - ec2-user -c`
sobre `/home/ec2-user/app-2-weather`.

Racional: el presupuesto de < 400 MB de runtime sobre 1 GB deja poco margen para el
build multietapa del frontend (`node:20-alpine` compilando Angular), que es donde la
instancia mata procesos OOM; el swap convierte ese OOM en lentitud. Persistirlo en
`/etc/fstab` con `grep -q` antes de añadir es lo que hace que sobreviva a un reinicio y a
una reejecución sin duplicar la línea.

`ec2-user` en el grupo `docker` evita que el despliegue del pipeline tenga que usar
`sudo docker compose`, y por eso el spec exige que el despliegue sea posible sin tocar la
configuración del servicio. Clonar como `ec2-user` (y no como root) evita que el
directório quede con propiedad de root, que es lo que rompe un `git pull` posterior desde
el pipeline SSH.

### 7. `tags` comunes por recurso en vez de `default_tags` del provider

Cada recurso lleva su bloque `tags` con `Name`, `Project = var.project_name` y
`ManagedBy = "terraform"`, en el sitio donde se declara.

Racional: `default_tags` del provider es la forma menos repetitiva, pero no se propaga a
todos los tipos de recurso ni a las relaciones, y su efecto es invisible al leer el HCL
de un recurso. Etiquetar en el sitio donde se declara hace auditable qué lleva cada
recurso y por qué, que es el objetivo del requisito de etiquetado del spec.

**Límite del esquema**: `aws_route_table_association` no admite bloque `tags` — su
esquema sólo acepta `route_table_id`, `subnet_id` y `gateway_id`—, verificado contra el
provider. La asociación es el único recurso del módulo en esa situación, y sigue siendo
localizable porque la subnet y la tabla de rutas que une sí llevan etiquetas. Declarar
`tags` ahí no es una decisión de diseño sino un error que el `terraform validate`
rechaza.

### 8. `.gitignore` del módulo con el patrón `*.tfstate*`, y el bloqueo del provider versionado

El `.gitignore` del módulo excluye `.terraform/`, `*.tfstate`, `*.tfstate.*`,
`crash.log`, `crash.*.log`, `*.tfvars`, `*.tfvars.json`, `override.tf`, `override_*.tf`,
`override_*.tf.json` y `*.tfplan`. El archivo de bloqueo `.terraform.lock.hcl` **no** se
excluye: se versiona.

Racional: el patrón `*.tfstate*` cubre también `terraform.tfstate.backup`, que es el
fichero que más veces acaba en un commit porque no tiene el nombre esperado y contiene la
misma información que el estado. Ignorar `*.tfvars` protege el `my_ip` del operador y
cualquier valor de entorno, dejando `terraform.tfvars.example` versionado porque el
patrón no lo cubre. Ignorar los `override_*` evita que una edición local de pruebas acabe
en el repositorio.

El bloqueo del provider se versiona porque es lo que la propia herramienta recomienda
al crearlo y porque contiene sólo la versión del provider y sus sumas de verificación, no
credenciales: excluirlo impediría fijar el provider, que es justamente lo que pide el
objetivo de que una copia limpia cree la misma infraestructura. El spec original pedía
excluirlo por analogía con el estado; se corrigió al contrastarlo con el comportamiento
real de Terraform.

Alternativa descartada: un único `.gitignore` en la raíz del repositorio. Se descartó
porque el módulo es autocontenido y alguien que copie sólo `infra/terraform/` a otro
proyecto necesita la protección viajando con él.

### 9. Una sola AZ, derivada por sufijo, sin `aws_availability_zones`

La subnet se fija con `availability_zone = "${var.aws_region}a"`.

Racional: `data.aws_availability_zones` puede devolver identificadores de AZ en formato
de cuenta (`use1-az1`) en vez de nombre de región (`us-east-1a`), y ese cambio ocurre sin
aviso; guardarlo en el estado provocaría un diff espurio de Availability Zone en el
plan. Para una instancia única sin HA, la letra es suficiente, determinista y estable. Si
alguna vez se quiere tolerar HA, la decisión se revisa con otro contexto.

Alternativa descartada: `data.aws_availability_zones` + `[0]`. Se descartó por el churn de
identificadores descrito y porque añade un recurso que sólo devuelve una constante.

### 10. Ningún bucket, usuario ni secreto se crea en el módulo

El módulo no crea IAM roles, access keys ni S3, y no llama a la API de Open-Meteo ni al
Data Lake. `user_data` sólo clona un repositorio público.

Racional: el contrato ya declara IAM y el backend remoto de estado como non-goals, y la
aplicación no consume AWS en runtime (sólo llama a Open-Meteo desde el contenedor). La
credencial de AWS del operador es una configuración local de su máquina. Añadir IAM aquí
sería superficie de privilegio sin consumidor.

### 11. Verificación local sin AWS: `fmt`, `validate` y una revisión del plan

La verificación de este change no aplica nada a AWS (eso costaría dinero y crearía
recursos reales). Se limita a `terraform init -backend=false`, `terraform validate` y
`terraform fmt -check` en `infra/terraform/`, más la comprobación de que el `.gitignore`
del módulo mantiene los ficheros de estado fuera de `git status`.

Racional: `validate` detecta errores de referencia, de tipo y de sintaxis sin
autenticarse, y `fmt -check` fija el formato sin depender de credenciales. El plan real
requiere credenciales y crearía la infraestructura; su revisión es una operación
deliberadamente manual y posterior, documentada en el README como paso del operador. Es
una limitación asumida del diseño, no un descuido: la verificación declarativa de la
corrección del plan está fuera del alcance de este change.

## Risks / Trade-offs

- **La AMI no está fijada → una actualización de AL2023 pide recrear la instancia** →
  Mitigación: es intencional; la instancia es desechable y recrearla vuelve a ejecutar
  `user_data`. Si hiciera falta reproducibilidad exacta, se declara `ami_id` como
  variable; no se hace por omisión para que los parches de seguridad lleguen solos.
- **Una IP de operador incorrecta deja la instancia inaccesible por SSH** → Mitigación:
  `my_ip` no tiene valor por omisión y se valida como `/32`; el pipeline usa la misma
  red por SSH que el operador, así que la IP pública de origen es la que espera. Se
  documenta en el README cómo recuperarla (crear una nueva clave en el par o usar la
  consola) sin rehacer el módulo.
- **`user_data` no se re-ejecuta si falla a mitad** → Cloud-init sólo corre el user-data
  del lanzamiento, así que un arranque fallido deja la instancia sin repo y sin
  complemento, sin señal visible desde fuera. Mitigación: el script marca el final con
  `touch /tmp/bootstrap-done`, y su consulta por SSH es la comprobación de salud del
  arranque; el README la documenta como paso de verificación. El script además es
  idempotente, así que `cloud-init` reintentable o una ejecución manual lo dejan bien.
- **`dnf update -y` al arrancar descarga la red lenta y puede fallar por
  indisponibilidad del mirror de AL2023** → Mitigación: el script usa `set -euo
  pipefail` para fallar rápido y el marker de fin permite distinguir "arrancó a medias" de
  "arrancó bien"; un fallo aquí se remedy con una ejecución manual, no con código nuevo.
- **`file(pathexpand(...))` requiere Terraform >= 1.3** → Una versión anterior falla con
  "function not found". Mitigación: la versión mínima queda escrita en el README y en un
  comentario del `variables.tf`; el `required_version` del provider no aplica al core, así
  que la dependencia se documenta, no se declara.
- **State local sin cifrar en el disco del operador** → Contiene la IP pública y el ARN
  de la instancia, no credenciales. Mitigación: `.gitignore` con `*.tfstate*` (decisión
  8); no hay backend remoto, así que el riesgo es acotado a la máquina local.
- **La instancia no tiene IAM instance profile** → Si en el futuro el despliegue
  consultara la API de EC2, fallaría por credenciales. Mitigación: el
  contrato no lo exige y es non-goal explícito; si hiciera falta, es una variable nueva en
  una capacidad nueva, no un parche de este módulo.
- **El `t3.micro` puede no estar disponible en todas las AZ/regiones** → Un apply en una
  región sin capacidad falla al crear la instancia. Mitigación: `us-east-1` es la región
  con capacidad de sobra y el error de AWS nombra la región; la variable `aws_region`
  permite cambiar sin editar código.

## Migration Plan

No hay migración: el repositorio nunca tuvo infraestructura AWS y este change la crea por
primera vez. No hay datos, usuarios ni despliegue previo que preservar.

Puesta en marcha, en orden (los pasos 1 y 2 los hace el operador en su máquina):

1. Generar el par de claves si no existe:
   `ssh-keygen -t ed25519 -f ~/.ssh/app2w-deploy -C app2w-deploy` (sin frase de paso,
   porque el pipeline la usa como secreto sin interacción).
2. Copiar `terraform.tfvars.example` a `terraform.tfvars` y fijar `my_ip` con la IP
   pública de salida del operador (por ejemplo, la que devuelve un servicio de consulta
   de IP).
3. `cd infra/terraform && terraform init && terraform fmt -check && terraform validate`.
4. Revisar el plan: `terraform plan` y comprobar que los recursos a crear son
   exactamente VPC, IGW, subnet, route table y asociación, security group, key pair,
   instancia y volumen, todos con nombre `app2w-*`.
5. `terraform apply`, y guardar la salida de `instance_public_ip` en el secreto
   `EC2_HOST` del entorno de producción y el contenido de `~/.ssh/app2w-deploy` en
   `EC2_SSH_KEY`.
6. Verificar el arranque por SSH con el `ssh_command` que imprime el output, y
   comprobar que existe el marker de fin del arranque.
7. Desplegar la aplicación: `cd ~/app-2-weather/infra && docker compose up -d --build`,
   y comprobar `curl "http://<ip>/api/prediction?date=<hoy>"`.

Rollback:

- Antes de aplicar: nada que deshacer; borrar `terraform.tfvars` y el directorio de
  trabajo.
- Después de aplicar: `terraform destroy` elimina VPC, subnet, tabla de rutas,
  security group, key pair e instancia. El key pair se elimina con el módulo, pero el par
  de claves local sigue existiendo (nunca lo creó Terraform).
- Si sólo falla el arranque de la instancia y la red está bien, no hace falta destruir:
  se re-ejecuta `user_data.sh` por SSH. Si hace falta una instancia nueva, `terraform taint` o
  `terraform apply -replace=aws_instance.web` sin tocar el resto.

## Open Questions

Ninguna que afecte a los specs, al enfoque o al desglose de tareas.

Desconocimientos que pueden resolverse durante la implementación sin cambiar estos
artefactos:

- La AMI concreta de AL2023 que resuelve `most_recent` hoy, que cambia con cada
  publicación de Amazon. No altera ningún requisito: el patrón y el filtro por `owners`
  son los que se especifican.
- El tiempo real de `dnf update -y` en el primer arranque, que depende de la región y
  del mirror. No cambia el script ni el spec; sólo condiciona cuánto se espera en el paso
  de verificación.
- El número exacto de versión del plugin de Compose v2 que se descarga. Se resuelve
  fijando la release en la URL del propio script; el requisito es "responde a su
  versión", no una versión concreta.