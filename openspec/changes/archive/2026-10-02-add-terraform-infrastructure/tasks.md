# Tasks

## 1. Andamiaje del módulo

- [x] 1.1 Crear el directorio `infra/terraform/` con los seis archivos del módulo (`main.tf`, `variables.tf`, `outputs.tf`, `user_data.sh`, `terraform.tfvars.example`, `.gitignore`) y verificar con `ls -a infra/terraform` que están los seis
- [x] 1.2 Escribir `infra/terraform/.gitignore` con los patrones `.terraform/`, `*.tfstate`, `*.tfstate.*`, `crash.log`, `crash.*.log`, `*.tfvars`, `*.tfvars.json`, `override.tf`, `override_*.tf`, `override_*.tf.json` y `*.tfplan`, y verificar con `git check-ignore -v` que ignora un `terraform.tfstate`, un `terraform.tfstate.backup` y un `terraform.tfvars` de prueba, y que `terraform.tfvars.example` no queda ignorado. El bloqueo `.terraform.lock.hcl` NO se excluye: se versiona porque fija el provider y no contiene secretos
- [x] 1.3 Ejecutar `terraform init -backend=false` en `infra/terraform` y verificar que descarga el provider `aws` v6.67.0 y crea `.terraform/` sin errores

## 2. Variables de entrada

- [x] 2.1 Declarar en `variables.tf` las cuatro variables del contrato (`aws_region` con default `us-east-1`, `my_ip` sin default, `public_key_path` con default `~/.ssh/app2w-deploy.pub`, `project_name` con default `app-2-weather`), cada una con `description` en español, y verificar con `terraform validate` que el módulo sigue siendo válido
- [x] 2.2 Añadir a `my_ip` una `validation` que exija un prefijo CIDR de host terminado en `/32` (regex `^[0-9]{1,3}(\.[0-9]{1,3}){3}/32$`) con un mensaje que indique el valor esperado y cómo obtener la IP, y verificar que `terraform plan` con `my_ip = "1.2.3.4/24"` falla con ese mensaje y que con `my_ip = "1.2.3.4/32"` deja de fallar por esa causa
- [x] 2.3 Añadir a `public_key_path` una `validation` no vacía y confirmar en un comentario que el módulo requiere Terraform >= 1.3 por el uso de `pathexpand`, y verificar que la variable sin valor falla en `terraform validate`
- [x] 2.4 Redactar `terraform.tfvars.example` con una entrada para cada variable y valores de muestra sustituibles (IP de ejemplo en `/32`), y verificar con `diff` contra la lista de variables de `variables.tf` que no falta ninguna y con `grep` que ninguna contiene una clave real

## 3. Red pública

- [x] 3.1 Declarar el bloque `provider "aws"` con `region = var.aws_region` y `required_providers` fijando la versión del provider AWS, y verificar con `terraform init -backend=false` que resuelve la versión fijada
- [x] 3.2 Crear `aws_vpc.main` con `cidr_block = "10.0.0.0/16"`, `enable_dns_support` y `enable_dns_hostnames` a `true`, y las etiquetas `Name = "app2w-vpc"`, `Project = var.project_name` y `ManagedBy = "terraform"`, y verificar con `terraform validate`
- [x] 3.3 Crear `aws_internet_gateway.main` con `vpc_id = aws_vpc.main.id` y su bloque de etiquetas, y crear `aws_subnet.public` con `cidr_block = "10.0.1.0/24"`, `availability_zone = "${var.aws_region}a"`, `map_public_ip_on_launch = true`, `vpc_id = aws_vpc.main.id` y sus etiquetas, y verificar con `terraform validate` que ambas referencias resuelven
- [x] 3.4 Crear `aws_route_table.public` con su ruta `cidr_block = "0.0.0.0/0"` hacia `aws_internet_gateway.main.id`, y la asociación `aws_route_table_association.public` con `route_table_id` y `subnet_id`, y verificar con `terraform validate` (la asociación no admite `tags`: su esquema sólo acepta `route_table_id`, `subnet_id` y `gateway_id`, por lo que la relación es localizable a través de la subnet y la tabla de rutas, que sí van etiquetadas)

## 4. Grupo de seguridad y acceso por SSH

- [x] 4.1 Crear `aws_security_group.web` con `vpc_id = aws_vpc.main.id`, sus etiquetas, un bloque `ingress` TCP 22 con `cidr_blocks = [var.my_ip]` y un `ingress` TCP 80 con `cidr_blocks = ["0.0.0.0/0"]`, y un `egress` a `["0.0.0.0/0"]`, y verificar con `terraform validate`
- [x] 4.2 Comprobar con `grep` sobre `main.tf` que el puerto 22 sólo aparece con `var.my_ip` y que no hay ninguna otra regla de `ingress` aparte de las dos del spec, y verificar con `terraform validate` que la lista de reglas coincide con la del spec
- [x] 4.3 Crear `aws_key_pair.deploy` con `key_name = "app2w-deploy"` y `public_key = file(pathexpand(var.public_key_path))`, y verificar que con una clave pública de prueba en `/tmp/prueba.pub` el plan muestra el material público y que `terraform validate` pasa con `pathexpand`

## 5. Instancia EC2

- [x] 5.1 Declarar `data "aws_ami" "al2023"` con `most_recent = true`, `owners = ["amazon"]` y `name_regex = "^al2023-ami-[0-9][0-9.]*-kernel-[0-9][0-9.]*-x86_64$"` (el provider v6 renombró `name_pattern`, y un glob flojo selecciona la variante `ecs-neuron-hvm`), y verificar con `terraform plan` contra la API real que resuelve `al2023-ami-2023.12.20260930.0-kernel-6.1-x86_64`
- [x] 5.2 Crear `aws_instance.web` con `ami = data.aws_ami.al2023.id`, `instance_type = "t3.micro"`, `key_name = aws_key_pair.deploy.key_name`, `associate_public_ip_address = true`, `user_data_base64 = base64encode(file("${path.module}/user_data.sh"))` (base64 porque el provider v6 advierte si `user_data` queda en claro en el estado), `subnet_id = aws_subnet.public.id`, `vpc_security_group_ids = [aws_security_group.web.id]` y sus etiquetas
- [x] 5.3 Declarar en `aws_instance.web` el bloque `root_block_device` con `volume_size = 8`, `volume_type = "gp3"` y `encrypted = true`, y verificar con `terraform validate` que el bloque es aceptado por el provider

## 6. Guión de arranque

- [x] 6.1 Escribir la cabecera de `user_data.sh` con `#!/bin/bash` y `set -euo pipefail`, un comentario que explique que cloud-init lo ejecuta en el primer arranque, y verificar con `bash -n user_data.sh` que la sintaxis es válida
- [x] 6.2 Implementar en `user_data.sh` la actualización del sistema y la instalación de `git`, añadiendo el repositorio de Docker y instalando `docker-ce`, `docker-ce-cli` y `containerd.io`, y verificar con `bash -n` y con `shellcheck` si está disponible
- [x] 6.3 Implementar en `user_data.sh` la descarga del binario de Docker Compose v2 a `/usr/local/lib/docker/cli-plugins/docker-compose` con `chmod +x`, y verificar con `bash -n` y con `grep` que la ruta y el permiso aparecen en el script
- [x] 6.4 Implementar en `user_data.sh` el `systemctl enable --now docker` y el alta de `ec2-user` en el grupo `docker`, y verificar con `bash -n` y con `grep` que el alta de grupo es idempotente (`getent group docker || usermod -aG docker ec2-user`)
- [x] 6.5 Implementar en `user_data.sh` la creación del swap de 2 GB con `fallocate`, `chmod 600`, `mkswap`, `swapon` y la línea idempotente en `/etc/fstab` protegida con `grep -q`, y verificar con `bash -n` y con `grep` que la línea de `/etc/fstab` sólo se añade si no existe
- [x] 6.6 Implementar en `user_data.sh` el `git clone` del repositorio en `/home/ec2-user/app-2-weather` ejecutado como `ec2-user` con `su - ec2-user -c`, y el `touch /tmp/bootstrap-done` final, y verificar con `bash -n` que el clon no se ejecuta como root
- [x] 6.7 Verificar la idempotencia del script completo revisando que ninguna operación destructiva se ejecuta sin condición previa (instalación de paquetes, alta de grupo, línea de `/etc/fstab`, creación del swap y el `touch` final), y anotar en un comentario del propio script que `cloud-init` lo ejecuta una sola vez pero que puede relanzarse a mano

## 7. Salidas

- [x] 7.1 Declarar en `outputs.tf` las salidas `instance_public_ip` y `instance_public_dns` desde los atributos públicos de `aws_instance.web`, y verificar con `terraform validate`
- [x] 7.2 Declarar la salida `ssh_command` componiendo `ssh -i ~/.ssh/app2w-deploy ec2-user@<public_ip>` con la interpolación de la IP pública y la clave privada local, y verificar con `terraform validate` y con `grep` que la cadena resultante no necesita edición manual

## 8. Verificación estática del módulo

- [x] 8.1 Ejecutar `terraform fmt -recursive` en `infra/terraform` y después `terraform fmt -check -recursive`, y verificar que el segundo comando sale con código 0
- [x] 8.2 Ejecutar `terraform validate` en `infra/terraform` y verificar que sale con código 0 y sin advertencias
- [x] 8.3 Ejecutar `terraform plan -refresh=false -input=false -var 'my_ip=203.0.113.10/32'` contra la API real de AWS (es de sólo lectura: no crea recursos) y verificar que los recursos a crear son exactamente ocho —VPC, gateway, subnet, tabla de rutas y asociación, security group, key pair e instancia, con el volumen raíz dentro de la instancia—, que los siete que admiten etiquetas llevan nombre `app2w-*` y `ManagedBy = terraform`, y que la AMI resuelta es la imagen base de AL2023 x86_64
- [x] 8.4 Comprobar que `git status --porcelain` no muestra `.terraform/`, ningún `*.tfstate*` ni `terraform.tfvars`, y que sí muestra los seis archivos del módulo como nuevos
- [x] 8.5 Comprobar sobre el plan (mismo contenido que iría al estado; no hay `terraform.tfstate` porque no se aplicó nada) que no aparece ninguna clave privada (buscar `PRIVATE KEY`) ni tokens de acceso de AWS, y verificar que del par de claves sólo está la mitad pública

## 9. Documentación del despliegue

- [x] 9.1 Añadir al `README.md` una sección de despliegue en AWS con la secuencia completa: generar `~/.ssh/app2w-deploy` con `ssh-keygen -t ed25519`, copiar `terraform.tfvars.example` a `terraform.tfvars` y fijar `my_ip`, ejecutar `terraform init/validate/plan/apply`, y leer el output `instance_public_ip`, y verificar que los comandos citados coinciden literalmente con los del módulo
- [x] 9.2 Documentar en el `README.md` la verificación del arranque por SSH (que `/tmp/bootstrap-done` existe, `docker compose version` responde y `swapon --show` lista el swap) y el comando de despliegue de la aplicación (`cd ~/app-2-weather/infra && docker compose up -d --build`), y verificar que la ruta del repositorio coincide con la del `user_data.sh`
- [x] 9.3 Documentar en el `README.md` el rollback con `terraform destroy` y la recuperación de una instancia inaccesible por SSH, y actualizar el bloque "Estructura" del `README.md` para incluir `infra/terraform/` junto a `infra/docker-compose.yml`, y verificar con `grep` que ambas rutas aparecen