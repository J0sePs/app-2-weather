# Proposal

## Why

La aplicación ya existe y se despliega en local con Docker Compose, pero no hay ninguna
forma reproducible de crear el entorno de destino en AWS: quien quiera desplegarla tiene
que provisionar VPC, subnet, reglas de seguridad, key pair e instancia EC2 a mano desde
la consola, y luego replicar a mano un arranque que ya está descrito en el contrato
(`openspec/project.md`, sección "Infrastructure as Code (Terraform)") pero que hoy sólo
existe como prosa.

Ese arranque a mano no es trivial y es el punto donde más fácil falla el despliegue:
Amazon Linux 2023 no trae el plugin `docker compose` v2 en la ruta que espera Docker,
una instancia `t3.micro` de 1 GB se queda sin memoria sin swap para buildear las imágenes,
y exponer el puerto 22 a `0.0.0.0/0` para "no quedarse fuera" expone la instancia a
escaneo. Este change convierte esa prosa en código declarativo, de modo que
`terraform apply` construya toda la infraestructura desde cero y `terraform destroy` la
elimine por completo, sin estado oculto en la consola.

## What Changes

- **Nuevo módulo Terraform en `infra/terraform/`** con seis archivos:
  `main.tf` (provider + red + instancia), `variables.tf`, `outputs.tf`,
  `user_data.sh`, `terraform.tfvars.example` y `.gitignore`.
- **Red pública mínima**: `aws_vpc.main` (`10.0.0.0/16`, DNS hostnames habilitado),
  `aws_internet_gateway.main`, `aws_subnet.public` (`10.0.1.0/24`, con IP pública
  asignada al lanzar), y `aws_route_table.public` con ruta por defecto `0.0.0.0/0` al
  gateway, asociada a esa subnet.
- **Security Group `app2w-web`**: TCP 22 sólo desde `var.my_ip/32`, TCP 80 desde
  `0.0.0.0/0`, egress a todo. El acceso por SSH queda atado a la IP que declara quien
  despliega, en lugar de abierto a Internet.
- **Key pair `app2w-deploy`** registrada a partir de la clave pública leída con
  `file(pathexpand(var.public_key_path))`, por omisión `~/.ssh/app2w-deploy.pub`. El
  par de claves no se crea en Terraform: la clave privada nunca entra en el estado.
- **Instancia `aws_instance.web`** de tipo `t3.micro` (Free Tier), con AMI de Amazon
  Linux 2023 resuelta por `data "aws_ami"` (`owners = ["amazon"]`,
  `name_pattern = "al2023-ami-*-x86_64"`, `most_recent = true`), IP pública asignada al
  lanzar, volumen raíz de 8 GB `gp3`, y `user_data` leído de `user_data.sh`.
- **Bootstrap de la instancia en `user_data.sh`**: actualiza el sistema e instala
  `docker` y `git`, habilita e inicia `docker` y añade `ec2-user` al grupo `docker`,
  instala el plugin `docker compose` v2 en `/usr/local/lib/docker/cli-plugins/`, crea
  un swap de 2 GB en `/swapfile` persistido en `/etc/fstab`, clona el repositorio en
  `/home/ec2-user/app-2-weather` como `ec2-user` y marca el final con
  `touch /tmp/bootstrap-done`.
- **Entradas parametrizadas**: `aws_region` (`us-east-1`), `my_ip` (sin valor por
  omisión, se lee de `terraform.tfvars`), `public_key_path` y `project_name`
  (`app-2-weather`). `my_ip` no tiene default a propósito: un default equivocado abriría
  SSH a un rango incorrecto sin que nadie lo note.
- **Outputs consultables**: `instance_public_ip` (destino del secreto de GitHub
  Actions), `instance_public_dns` y `ssh_command` con la invocación `ssh` lista para
  pegar.
- **Etiquetado uniforme**: todos los recursos llevan `Name` con prefijo `app2w-` más
  `Project` y `ManagedBy` mediante un bloque `tags` común.
- **Estado y credenciales fuera del repositorio**: el `.gitignore` del módulo excluye
  `.terraform/`, `*.tfstate*`, `terraform.tfvars` y los archivos de lock de proveedor,
  de modo que ni el estado (que contiene la IP pública y el ARN de la instancia) ni la
  clave `my_ip` del operador lleguen a un commit.

### Decisiones de alcance tomadas en el proposal

- **Nombres de clave según el contrato**: el key pair y el `ssh_command` usan
  `app2w-deploy`, tal y como fija `openspec/project.md` y como espera el secreto
  `EC2_SSH_KEY` del pipeline. La clave local `~/.ssh/weather-deploy` que existe en la
  máquina de desarrollo no se reutiliza; `public_key_path` queda como variable para
  quien prefiera otro par.
- **Sin `terraform.tfvars` versionado**: se versiona sólo `terraform.tfvars.example`, y
  el `.gitignore` del módulo ignora el `.tfvars` real, que contiene la IP del operador.
- **Una sola zona de disponibilidad**: la subnet se fija en el sufijo `a` de
  `var.aws_region` en lugar de consultar `aws_availability_zones`. Para una instancia
  única sin alta disponibilidad es determinista y evita el churn de IDs de AZ que AWS
  reporta de forma distinta por cuenta.
- **Documentación de uso en el README**: el `README.md` tiene una sección "Estructura"
  que hoy sólo lista `infra/docker-compose.yml`; este change la actualiza con
  `infra/terraform/` y con los comandos de despliegue, para que el flujo no viva sólo
  en los specs.

## Capabilities

### New Capabilities

- `infrastructure-as-code`: definición declarativa en Terraform de la red pública, el
  security group, el key pair y la instancia EC2 `t3.micro` que hospeda la aplicación;
  el script de arranque idempotente que prepara esa instancia (Docker, Docker Compose,
  swap de 2 GB y clon del repositorio); el contrato de variables de entrada y de
  outputs que conecta el despliegue con el pipeline; y las exclusiones de estado y
  credenciales del control de versiones.

### Modified Capabilities

Ninguna. `containerized-deployment` sigue exigiendo exactamente lo mismo —las mismas
dos imágenes y el mismo `infra/docker-compose.yml`—: este change no lo altera, sólo
define el host donde se ejecuta. `data-lake`, `visitor-prediction` y
`prediction-web-ui` quedan intactos.

## Impact

- **Código nuevo**: `infra/terraform/` (seis archivos). `infra/docker-compose.yml` no
  se toca.
- **Documentación**: una sección nueva de despliegue en `README.md` y la actualización
  de su sección "Estructura".
- **Recursos AWS nuevos** (todos eradication por `terraform destroy`): 1 VPC, 1 Internet
  Gateway, 1 subnet pública, 1 route table con su asociación, 1 security group, 1 key
  pair, 1 instancia EC2 y su EBS de 8 GB `gp3`. Todos etiquetados con
  `Project=app-2-weather` y `ManagedBy=terraform`.
- **Costes**: una instancia `t3.micro` y un volumen `gp3` de 8 GB, dentro de los límites
  del Free Tier durante el periodo de cortesía; fuera de él, bajo una factura de pocos
  dólares al mes.
- **Dependencias**: Terraform >= 1.3 en la máquina del operador (para `pathexpand`) y
  credenciales AWS con permisos sobre EC2, VPC y el servicio de key pairs. No se
  requieren plugins, módulos externos ni backends remotos.
- **Seguridad**: el estado de Terraform contiene la IP pública de la instancia y el
  `my_ip` del operador, por lo que se mantiene local e ignorado por git; la clave
  privada `app2w-deploy` se genera fuera de Terraform y sólo se usa como secreto del
  pipeline. Ninguna credencial se versiona.
- **Dependencia del pipeline**: el output `instance_public_ip` es el valor que
  consumen los secretos `EC2_HOST` y `EC2_SSH_KEY` del workflow de GitHub Actions. Ese
  workflow es una sección distinta del contrato y queda como cambio posterior; este
  change no lo crea.