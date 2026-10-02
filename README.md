# Predicción de Afluencia - Machu Picchu

Estima cuántos visitantes se esperan en Machu Picchu a partir del pronóstico del clima
de Open-Meteo y de un historial sintético de dos años. Sin cuentas, sin claves de API
y sin servicios de pago.

La estimación **no es un dato oficial**: el historial es sintético y la tarjeta de
resultado lo advierte siempre en pantalla.

## Despliegue en AWS con Terraform

La infraestructura de destino (VPC, subnet, grupo de seguridad, par de claves e
instancia EC2 `t3.micro`) se define en `infra/terraform/`. Un `terraform apply` la crea
entera desde cero y un `terraform destroy` la elimina.

Hace falta Terraform >= 1.3 (el módulo usa `pathexpand()`), credenciales de AWS y una
dirección IP pública propia para restringir el acceso por SSH.

### 1. Generar el par de claves

Sin frase de paso, porque el pipeline la usa como secreto sin interacción:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/app2w-deploy -C app2w-deploy
```

### 2. Configurar las variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edita `terraform.tfvars` y pon tu IP pública de salida con prefijo `/32`:

```bash
curl -s https://checkip.amazonaws.com    # ej.: 203.0.113.10 -> my_ip = "203.0.113.10/32"
```

`my_ip` no tiene valor por omisión a propósito: es el único origen permitido para el
puerto 22, y un valor por omisión sería un rango abierto a Internet que nadie revisa. El
archivo `terraform.tfvars` está en el `.gitignore` del módulo; sólo se versiona el
`.example`.

### 3. Crear la infraestructura

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan      # revisa la lista antes de continuar
terraform apply
```

El plan debe crear exactamente ocho recursos: VPC, gateway de Internet, subnet, tabla de
rutas y su asociación, grupo de seguridad, par de claves e instancia.

### 4. Verificar el arranque

La salida `ssh_command` lleva el comando de conexión listo para pegar:

```bash
terraform output ssh_command
```

El arranque de la instancia es asíncrono y dura varios minutos (actualiza el sistema e
instala Docker). La marca de fin del arranque es la primera comprobación:

```bash
ssh -i ~/.ssh/app2w-deploy ec2-user@<ip>
ls /tmp/bootstrap-done        # si existe, el arranque terminó bien
docker compose version        # responde si el complemento v2 está instalado
swapon --show                 # lista la unidad de 2 GB
```

Si `/tmp/bootstrap-done` no existe, el arranque se quedó a mitad. El arranque termina en
`dnf update -y`, que es donde falla si el mirror de Amazon no responde. Se relanza a mano
desde SSH —el script está en el clon, no en la instancia—:

```bash
bash ~/app-2-weather/infra/terraform/user_data.sh
```

### 5. Desplegar la aplicación

El arranque deja el repositorio clonado, así que en la instancia:

```bash
cd ~/app-2-weather/infra
docker compose up -d --build
```

Este es el camino de la primera publicación y el de recuperación; las siguientes ocurren
solas al integrar en `main` (ver «Integración y despliegue continuos»).

Y comprobar desde fuera:

```bash
curl "http://<ip>/api/prediction?date=$(TZ=America/Lima date +%F)"
```

### 6. Secretos del pipeline

`terraform output instance_public_ip` es el valor del secreto `EC2_HOST`, `ec2-user` es el
de `EC2_USER`, y el contenido de `~/.ssh/app2w-deploy` (la clave privada) es el de
`EC2_SSH_KEY`. Los tres se dan de alta como secretos del entorno `production`; el
procedimiento está en «Integración y despliegue continuos».

### Deshacer

```bash
terraform destroy
```

Elimina VPC, subnet, tabla de rutas, grupo de seguridad, par de claves e instancia. El
par de claves local `~/.ssh/app2w-deploy` no se toca: nunca lo creó Terraform.

Si sólo falla el arranque, no hace falta destruir nada: basta con relanzar
`user_data.sh` por SSH. Si hay que reemplazar la instancia sin tocar el resto:

```bash
terraform apply -replace=aws_instance.web
```

### Si la instancia queda inaccesible por SSH

Casi siempre es que `my_ip` no coincide con la IP pública de salida. El puerto 22 sólo
acepta ese `/32`. Se recupera desde la consola de AWS (Session Manager no está
disponible porque el módulo no crea un IAM instance profile) o añadiendo una clave nueva
al par `app2w-deploy` desde la consola. Para cambiar el origen:

```bash
terraform apply -var 'my_ip=<tu-ip>/32'
```

### Notas

- La AMI se resuelve en el plan contra el catálogo de AWS (Amazon Linux 2023, `x86_64`,
  la más reciente). No está fijada a propósito: cuando Amazon publica una versión nueva,
  el plan pide recrear la instancia, y recrearla vuelve a ejecutar el arranque.
- El estado queda en `terraform.tfstate`, en local e ignorado por git. Contiene la IP
  pública y el ARN de la instancia, pero ninguna credencial.

## Integración y despliegue continuos

`.github/workflows/ci-cd.yml` define un flujo con tres trabajos:

| Trabajo | Cuándo corre | Qué hace |
| --- | --- | --- |
| `backend-test` | PR a `main` y `push` a `main` | `uv sync --frozen` y `uv run pytest` en Python 3.12. |
| `frontend-test` | PR a `main` y `push` a `main` | `npm ci` y `npm run test:ci` en Node 20 con Chrome headless. |
| `deploy` | sólo `push` a `main` | Se conecta por SSH y reconstruye los servicios en la instancia. |

`deploy` depende de los dos trabajos de prueba: si cualquiera falla, GitHub lo marca como
omitido y no publica. Una pull request en verde nunca despliega.

El despliegue se construye **en la instancia**, no en el runner: el intercambio de 2 GB
que instaló `user_data.sh` es lo que permite el build multietapa del frontend en una
`t3.micro` de 1 GB. Por eso puede tardar varios minutos.

### Alta del entorno `production` (una vez, en GitHub)

El flujo no lleva secretos ni reglas de protección en el repositorio: eso vive en el
entorno, y por eso el trabajo `deploy` declara `environment: production`.

1. Crear el entorno en **Settings → Environments → New environment**, con el nombre
   `production`.
2. En **Required reviewers**, activar la regla y añadir al menos un revisor. Sin esto el
   despliegue saldría sin revisión de nadie.
3. Añadir los tres secretos del entorno (**Environment secrets**, no *repository
   secrets*):

   | Secreto | Valor |
   | --- | --- |
   | `EC2_HOST` | `terraform output instance_public_ip` de `infra/terraform` |
   | `EC2_USER` | `ec2-user` |
   | `EC2_SSH_KEY` | contenido íntegro de `~/.ssh/app2w-deploy` |

   La clave se pega como multilínea y no debe tener frase de paso, porque el pipeline no
   puede escribirla en un prompt.

Los secretos son **del entorno**, no del repositorio, a propósito: así los trabajos de
prueba de una pull request abierta por un tercero nunca ven material de acceso al
servidor.

### Qué ejecuta el despliegue

```bash
set -e
cd ~/app-2-weather
git pull origin main
cd infra
docker compose up -d --build
docker image prune -f
```

`set -e` hace que un fallo intermedio no continúe hasta un paso que depende de él. No hay
`sudo`: el usuario de la instancia ya está en el grupo `docker`.

### Publicar

Integrar en `main` y aprobar la ejecución en espera. El trabajo aparece como
*waiting for approval* en la pestaña **Actions**.

### Reversión

No hay rollback automático: una publicación fallida se deshace a mano, desde la
instancia.

```bash
ssh -i ~/.ssh/app2w-deploy ec2-user@<ip>
cd ~/app-2-weather
git reset --hard <commit-anterior>
cd infra && docker compose up -d --build
```

Mientras tanto, un despliegue que falla a mitad deja los contenedores anteriores en
servicio: `up -d` no para el servicio que no llegó a reconstruirse.

### Alcance

No hay *smoke tests* posteriores al despliegue: se considera correcto cuando el script
termina con código cero. Tampoco hay `plan`/`apply` de Terraform en el pipeline —la
infraestructura se cambia a mano con `terraform apply`— ni publicación de imágenes en un
registro: se construyen y se sirven desde la misma instancia.

## Despliegue

Sólo hace falta Docker. Desde el clon:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Y abrir <http://localhost>. La UI y la API se sirven desde el mismo origen: Nginx
sirve la aplicación y hace de proxy inverso de `/api/` hacia el backend, de modo que
el navegador no necesita CORS.

Para comprobar que responde:

```bash
docker compose -f infra/docker-compose.yml ps                       # ambos servicios "healthy"
curl "http://localhost/api/prediction?date=$(TZ=America/Lima date +%F)"
```

Para detenerlo:

```bash
docker compose -f infra/docker-compose.yml down
```

## Desarrollo

### Backend

Requiere Python 3.12 y [`uv`](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync                                      # resuelve el entorno
uv run python -m datalake.generate_datalake  # regenera el Data Lake canónico
uv run uvicorn app.main:app --reload          # http://127.0.0.1:8000
```

El CSV del Data Lake viene incluido en el repositorio, así que el generador sólo hace
falta si cambian sus reglas. Es determinista: con la misma configuración produce
siempre el mismo archivo.

La configuración tiene valores por omisión funcionales y se ajusta con variables
`MP_`:

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MP_RUTA_DATALAKE` | `backend/datalake/machupicchu_history.csv` | Ruta del CSV del historial. |
| `MP_OPEN_METEO_BASE_URL` | `https://api.open-meteo.com/v1/forecast` | Endpoint del pronóstico. |
| `MP_OPEN_METEO_TIMEOUT` | `4.0` | Segundos de espera antes de un `502`. |
| `MP_CORS_ORIGINS` | `["http://localhost:4200", "http://127.0.0.1:4200"]` | Orígenes permitidos, como JSON. |
| `MP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` o `CRITICAL`. |

Documentación interactiva de la API en <http://127.0.0.1:8000/docs>.

### Frontend

Requiere Node 20.

```bash
cd frontend
npm install
npm start            # http://localhost:4200, con proxy a :8000
```

`proxy.conf.json` reenvía `/api` al backend del puerto 8000, igual que Nginx en
producción. Si el backend vive en otro puerto, se ajusta ese archivo.

## Tests

```bash
# Backend: 286 pruebas, con umbral de cobertura del 80 %.
cd backend && uv run pytest

# Frontend: 78 pruebas en Chrome headless (necesita CHROME_BIN o un Chrome instalado).
cd frontend && npm run test:ci

# Verificación del Data Lake y la compilación de la aplicación.
cd frontend && npm run build
```

## Estructura

```
.github/
  workflows/
    ci-cd.yml     Pruebas de backend y frontend, y despliegue por SSH a la instancia
backend/
  app/            API FastAPI: Data Lake, clima, predicción y rutas
  datalake/       Generador del historial sintético y el CSV versionado
  tests/          Pruebas del backend
frontend/
  src/app/        SPA Angular: página, tarjeta de resultado y cliente de la API
  nginx/          Configuración de Nginx que sirve la SPA y hace de proxy
infra/
  terraform/      Infraestructura AWS: red, security group, EC2 y arranque
  docker-compose.yml
```

## API

| Ruta | Qué hace |
| --- | --- |
| `GET /api/prediction?date=YYYY-MM-DD` | Predicción de afluencia. Sin `date`, usa hoy en `America/Lima`. |
| `GET /health` | Sonda de salud. No consulta ni el clima ni el Data Lake. |
| `GET /docs` | Documentación OpenAPI interactiva. |

Errores: `422` si la fecha tiene un formato inválido, ya pasó o está fuera de la
ventana del proveedor; `502` si no se puede obtener el pronóstico.
