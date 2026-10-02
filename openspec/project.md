# Machu Picchu Visitor Predictor & Data Lake

## Purpose
Aplicación web minimalista para predecir la afluencia de turistas a Machu Picchu (Cuzco) para el día de hoy o cualquier fecha seleccionada por el usuario. Cruza el pronóstico meteorológico obtenido de Open-Meteo con un Data Lake sintético en CSV de 2 años de historial para estimar la cantidad de visitantes y el porcentaje de aforo.

## Tech Stack

### Backend
- **Language:** Python 3.12
- **Framework:** FastAPI 0.115+
- **ASGI server:** uvicorn 0.32+
- **Package manager:** uv (usar pyproject.toml)
- **HTTP client:** httpx 0.28+ (para consumir Open-Meteo)
- **Validation:** pydantic 2.10+ y pydantic-settings
- **Data Lake Engine:** Lector nativo en Python de archivos CSV locales

### Frontend
- **Framework:** Angular 20 (standalone components + signals)
- **Package manager:** npm
- **SSR:** desactivado (SPA pura)
- **Estilos:** CSS puro responsivo
- **HTTP:** HttpClient
- **UI Controls:** Input de fecha nativo (`<input type="date">`) con valor por defecto en la fecha actual

### External APIs
- **Open-Meteo API** (gratis, sin API key):
  - Coordenadas de Machu Picchu: `latitude=-13.1631&longitude=-72.5450`
  - Endpoint de pronóstico diario: `https://api.open-meteo.com/v1/forecast?latitude=-13.1631&longitude=-72.5450&daily=temperature_2m_max,precipitation_probability_max,weathercode&timezone=auto`

### Data Lake (CSV)
- **Archivo:** `backend/datalake/machupicchu_history.csv`
- **Registros:** 730 días sintéticos (2 años) con columnas:
  `fecha,dia_semana,temporada,clima,temperatura_c,es_fin_de_semana_o_feriado,visitantes_reales`
- **Reglas del negocio:**
  - Capacidad máxima oficial: 5,600 personas/día.
  - Temporada seca (mayo-octubre): alta afluencia base (~4,000 - 5,200).
  - Temporada de lluvias (noviembre-abril): afluencia baja (~1,800 - 3,200).
  - Lluvia torrencial o tormenta: reduce visitas.
  - Fin de semana y feriado: aumenta afluencia (+15%).

### Prediction Logic
- Entrada: Fecha seleccionada (`target_date`) en formato YYYY-MM-DD (por defecto hoy).
- Proceso:
  1. Obtiene el clima pronosticado para esa fecha en Machu Picchu.
  2. Identifica si la fecha es fin de semana y su temporada (mes).
  3. Filtra registros similares en el CSV del Data Lake y promedia los visitantes.
  4. Calcula el nivel de afluencia:
     - "Bajo" (< 3,000 personas)
     - "Moderado" (3,000 a 4,500 personas)
     - "Alto" (> 4,500 personas)

## API Endpoints
- `GET /api/prediction?date=YYYY-MM-DD` → Devuelve:
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
- `GET /health` → Devuelve `{"status": "ok"}`

## Frontend UI
- Encabezado: "Predicción de Afluencia - Machu Picchu".
- Barra de control:
  - Input selector de fecha con icono de calendario (`<input type="date">`).
  - Botón "Consultar Afluencia".
- Tarjeta de resultado (`PredictionCard`):
  - Clima esperado: Temperatura y condición atmosférica.
  - Visitantes estimados: `~4,580 personas`.
  - Barra de capacidad o porcentaje: `82% del aforo permitido`.
  - Etiqueta de nivel: `Afluencia Alta`.

## Testing & Quality
- Pytest en backend con umbral mínimo de 80% (`--cov-fail-under=80`).
- Mocking de llamadas a Open-Meteo usando `respx`.

## Infrastructure & Constraints
- Docker Compose v2 con 2 servicios:
  - `backend`: `python:3.12-slim` en puerto interno 8000.
  - `frontend`: Multi-stage (`node:20-alpine` -> `nginx:1.27-alpine`), expone solo puerto 80 y hace proxy de `/api/*` al backend.
- Memoria total en runtime < 400 MB (orientado a EC2 t3.micro con 1 GB RAM).



## Infrastructure as Code (Terraform)

### Estrategia
- Toda la infraestructura AWS se define en **Terraform** bajo `infra/terraform/`.
- Estado local en `terraform.tfstate` (añadido al `.gitignore`).
- **Un solo comando** (`terraform apply`) crea TODA la infra desde cero.
- **user_data** del EC2 instala automáticamente: Docker, Docker Compose, Buildx, Git, swap 2 GB.

### Archivos requeridos
```
infra/terraform/
├── main.tf              # provider + resources
├── variables.tf         # input variables
├── outputs.tf           # instance_public_ip, ssh_command
├── user_data.sh         # bootstrap script for EC2
├── terraform.tfvars.example
└── .gitignore           # ignore .tfstate, .terraform/
```

### Recursos AWS (todos con prefijo `app2w-` y tags `{Project=app-2-weather, ManagedBy=terraform}`)
- **VPC**: `aws_vpc.main` con CIDR `10.0.0.0/16`, DNS hostnames enabled.
- **Internet Gateway**: `aws_internet_gateway.main` attached a la VPC.
- **Subnet pública**: `aws_subnet.public` con CIDR `10.0.1.0/24`, `map_public_ip_on_launch = true`.
- **Route Table pública**: default route `0.0.0.0/0 → igw`, asociada a la subnet.
- **Security Group**: `aws_security_group.web`:
  - Ingress TCP 22 desde `var.my_ip` (CIDR `/32`).
  - Ingress TCP 80 desde `0.0.0.0/0`.
  - Egress all.
- **Key Pair**: `aws_key_pair.deploy` registrando la pública `~/.ssh/app2w-deploy.pub` leída vía `file()`.
- **EC2 Instance**: `aws_instance.web`:
  - AMI: Amazon Linux 2023 (resolución con `aws_ami` data source, owners `amazon`).
  - Instance type: `t3.micro` (Free Tier).
  - Associate public IP: true.
  - `user_data` desde `file("user_data.sh")`.
  - Root block device: 8 GB `gp3`.

### Variables (`variables.tf`)
- `aws_region` (default `us-east-1`).
- `my_ip` (string, CIDR `/32` — no default, se lee de `terraform.tfvars`).
- `public_key_path` (default `~/.ssh/app2w-deploy.pub`).
- `project_name` (default `app-2-weather`).

### Outputs (`outputs.tf`)
- `instance_public_ip` — IP para GitHub Actions secret.
- `instance_public_dns`.
- `ssh_command` — comando listo para pegar: `ssh -i ~/.ssh/app2w-deploy ec2-user@<ip>`.

### Script `user_data.sh`
Ejecuta al primer boot:
1. `dnf update -y`.
2. `dnf install -y git docker` (desde los repos nativos de Amazon Linux 2023 — NO usar el repo externo de Docker porque no publica para Amazon Linux).
2. Enable + start `docker`, add `ec2-user` al grupo `docker`.
3. Instala `docker compose` v2 plugin en `/usr/local/lib/docker/cli-plugins/`.
4. Crea swap de 2 GB en `/swapfile` y persiste en `/etc/fstab`.
5. `git clone https://github.com/J0sePs/app-2-weather.git /home/ec2-user/app-2-weather` como `ec2-user`.
6. Marca el final con `touch /tmp/bootstrap-done`.

### Non-goals (para este change)
- Backend remoto de Terraform state (S3 + DynamoDB) — se mantiene state local.
- IAM roles/instance profiles — la app no necesita acceso a AWS en runtime.
- RDS, Load Balancer, Route 53 — fuera de alcance.
- Múltiples AZs o Auto Scaling — single instance basta.

## CI/CD con GitHub Actions

### Estrategia
- Pipeline **minimalista**: tests → approval → deploy vía SSH.
- Build en la EC2 (reutiliza el swap que `user_data` ya configuró).
- Reutiliza la misma `app2w-deploy` SSH key que Terraform registró en AWS.

### Workflow (`.github/workflows/ci-cd.yml`)
- **Triggers**:
  - `pull_request` → `main` → corre tests.
  - `push` → `main` → corre tests + deploy con approval.
- **Jobs**:
  1. `backend-test`: Ubuntu 22.04, `astral-sh/setup-uv@v3`, `uv python install 3.12`, `uv sync --frozen`, `uv run pytest`.
  2. `frontend-test`: Ubuntu 22.04, `actions/setup-node@v4` Node 20, `npm ci`, `npm run test:ci`.
  3. `deploy`: solo en `push` a `main`. Depende de ambos tests. `environment: production`. Usa `appleboy/ssh-action@v1.0.3`.

### Deploy script (SSH remoto)
```bash
set -e
cd ~/app-2-weather
git pull origin main
cd infra
docker compose up -d --build
docker image prune -f
```

### GitHub Environment `production`
- **Protection rules**: required reviewers (mínimo 1).
- **Environment secrets**:
  - `EC2_HOST` — valor del output `instance_public_ip` de Terraform.
  - `EC2_USER` — `ec2-user`.
  - `EC2_SSH_KEY` — contenido completo de `~/.ssh/app2w-deploy` (privada).

### Non-goals (para este change)
- Build de imágenes Docker en GHCR — se buildea en EC2 directamente.
- Rollback automático — manual con `git reset --hard` + rebuild.
- Smoke tests post-deploy — futuro.