# Proposal

## Why

El despliegue a la instancia EC2 es hoy manual: alguien entra por SSH y lanza
`docker compose up -d --build` a mano, sin que nada compruebe antes que la aplicación
sigue healthy. El backend ya exige 80 % de cobertura en `pyproject.toml` y el frontend
tiene specs de Jasmine/Karma que sólo se ejecutan en el portátil del operador, de modo
que un cambio roto puede llegar a producción sin que ninguna verificación automática lo
detecte. Con la infraestructura ya definida en Terraform y el arranque de la instancia
clonando el repositorio en `~/app-2-weather`, falta únicamente el eslabón que verifica
y publica: un pipeline que ejecute los tests en cada pull request y despliegue
`main` tras una aprobación explícita.

## What Changes

- Se añade el fichero de workflow `.github/workflows/ci-cd.yml` con tres trabajos:
  `backend-test` (Ubuntu 22.04 + `astral-sh/setup-uv@v3` + `uv sync --frozen` + pytest),
  `frontend-test` (Node 20 + `npm ci` + `npm run test:ci`) y `deploy`.
- El workflow se dispara en `pull_request` hacia `main` (sólo tests) y en `push` a
  `main` (tests + deploy).
- El trabajo `deploy` se condiciona a `push` sobre `main`, depende de ambos trabajos de
  test, declara `environment: production` para que GitHub exija la aprobación de un
  revisor, y se conecta por SSH con `appleboy/ssh-action@v1.0.3`.
- El script remoto de despliegue se ejecuta con `set -e` y encadena
  `cd ~/app-2-weather && git pull origin main && cd infra && docker compose up -d --build
  && docker image prune -f`.
- Se documenta la configuración del GitHub Environment `production` (regla de revisores
  requeridos y secretos `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`), que se crea en la interfaz
  de GitHub y no en el repositorio.
- Se añade el script `test:ci` a `frontend/package.json`
  (`ng test --watch=false --browsers=ChromeHeadless`), porque hoy no existe y `npm run
  test` arranca Karma en modo interactivo, que no termina nunca en un runner.
- El trabajo `frontend-test` instala Chrome en el runner, requisito del lanzador Karma
  que el proyecto ya usa.

No hay cambios rompientes: no se toca la API, ni las imágenes, ni la configuración de
Compose, ni el módulo Terraform.

## Capabilities

### New Capabilities

- `ci-cd`: verificación automática de backend y frontend en cada pull request hacia
  `main`, y despliegue a la instancia EC2 por SSH tras una aprobación, con la
  configuración y los secretos del entorno de producción declarados de forma explícita.

### Modified Capabilities

Ninguna. `containerized-deployment` describe las imágenes y la orquestación, cuyo
comportamiento no cambia: el pipeline se limita a invocar `docker compose up -d --build`
sobre la configuración existente. `infrastructure-as-code` ya declara que el pipeline
consume `instance_public_ip` y la clave `app2w-deploy`, y esta decisión es la que lo
consolida.

## Impact

- **Ficheros nuevos:** `.github/workflows/ci-cd.yml`.
- **Ficheros modificados:** `frontend/package.json` (se añade únicamente el script
  `test:ci`; no cambian dependencias ni la configuración de compilación).
- **Documentación:** sección de CI/CD en el README y en `openspec/project.md`, para
  dejar escrito el procedimiento de alta de secretos, que es manual.
- **Dependencias en tiempo de ejecución:** ninguna. No se añaden acciones de terceros más
  allá de `astral-sh/setup-uv@v3`, `actions/setup-node@v4`,
  `browser-actions/setup-chrome@v1` y `appleboy/ssh-action@v1.0.3`, todas invocadas por
  versión fija.
- **Sistemas externos:** el GitHub Environment `production`, que aporta la aprobación
  manual y los tres secretos de conexión SSH.
- **Precondiciones ya satisfechas por cambios anteriores:** `backend/uv.lock` y
  `frontend/package-lock.json` están versionados, de modo que `--frozen` y `npm ci`
  resuelven de forma reproducible; `infra/docker-compose.yml` define los servicios que
  el script remoto levanta; `infra/terraform/user_data.sh` deja el repositorio clonado
  en `/home/ec2-user/app-2-weather` como `ec2-user`, sin lo que el `git pull` por SSH
  fallaría por permisos.
- **Riesgo asumido:** la clave privada `app2w-deploy` se almacena como secreto del
  entorno de GitHub además de existir en la máquina del operador. Es el mismo material
  que Terraform ya registró en AWS y no se versiona en el repositorio.