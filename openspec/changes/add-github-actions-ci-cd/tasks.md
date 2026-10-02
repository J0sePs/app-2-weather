# Tasks

## 1. Comando de verificación del frontend

- [x] 1.1 Añadir `"test:ci": "ng test --watch=false --browsers=ChromeHeadless"` al bloque `scripts` de `frontend/package.json`, sin tocar dependencias ni el resto de scripts, y verificar ejecutando `npm run test:ci` en `frontend/` que la suite termina sola, con código de salida 0 y sin esperar entrada por consola
- [x] 1.2 Confirmar que `npm run test` sigue intacto para el uso local y verificar que la suite falla con código distinto de 0 cuando se introduce un fallo temporal en una spec y luego se revierte

## 2. Flujo de trabajo

- [x] 2.1 Crear `.github/workflows/ci-cd.yml` con el bloque `name`, los disparadores `pull_request` sobre `main` y `push` sobre `main`, `permissions: contents: read` y `concurrency` por referencia con cancelación sólo fuera de `main`; verificar que el YAML se analiza sin error y que `on:` no incluye ningún otro evento ni rama
- [x] 2.2 Añadir el trabajo `backend-test` sobre `ubuntu-22.04` con `astral-sh/setup-uv@v3`, instalación de Python 3.12, `uv sync --frozen` y `uv run pytest` con `working-directory: backend`; verificar que el umbral `--cov-fail-under=80` de `backend/pyproject.toml` se aplica sin declararlo otra vez en el workflow
- [x] 2.3 Añadir el trabajo `frontend-test` sobre `ubuntu-22.04` con `actions/setup-node@v4` en Node 20 y caché de npm, `browser-actions/setup-chrome@v1`, `npm ci` y `npm run test:ci` con `working-directory: frontend`; verificar que ninguna de las acciones se referencia por rama o etiqueta móvil
- [x] 2.4 Añadir el trabajo `deploy` con `needs: [backend-test, frontend-test]`, condición `github.event_name == 'push'`, `environment: production` y `timeout-minutes` holgado; verificar que un workflow con `github.event_name` igual a `pull_request` no alcanza el trabajo
- [x] 2.5 Implementar en el paso `script` de `appleboy/ssh-action@v1.0.3` el bloque `set -e` seguido de `cd ~/app-2-weather`, `git pull origin main`, `cd infra`, `docker compose up -d --build` y `docker image prune -f`, con el directorio de trabajo en el checkout; verificar que la ruta del paso 1 coincide con `REPO_DIR` de `infra/terraform/user_data.sh` y que ningún comando invoca `sudo`
- [x] 2.6 Resolver los tres secretos de `production` (`${{ secrets.EC2_HOST }}`, `${{ secrets.EC2_USER }}`, `${{ secrets.EC2_SSH_KEY }}`) escribiendo la clave privada en un archivo temporal con permisos `600` en el runner; verificar que el fichero de workflow no contiene ningún valor literal de host, usuario o clave

## 3. Verificación del flujo

- [x] 3.1 Validar la sintaxis de `.github/workflows/ci-cd.yml` con el analizador de Actions (por ejemplo `actionlint`) y confirmar que no reporta errores; si `actionlint` no está disponible, verificar al menos el análisis del YAML y la presencia de los tres trabajos con sus claves requeridas
- [x] 3.2 Reproducir localmente la secuencia exacta del trabajo `backend-test` (`uv sync --frozen` y `uv run pytest` desde `backend/`) y confirmar que termina con código 0
- [ ] 3.3 Abrir una pull request de prueba hacia `main` y verificar en la ejecución resultante que corren `backend-test` y `frontend-test`, que no hay ningún trabajo de despliegue y que la inspección de los trabajos no revela secretos de `production`

## 4. Documentación y prerrequisitos manuales

- [x] 4.1 Documentar en `README.md` el alta del GitHub Environment `production` con la regla de revisores requeridos y los secretos `EC2_HOST` (desde `terraform output instance_public_ip`), `EC2_USER` (`ec2-user`) y `EC2_SSH_KEY`; verificar que el procedimiento es reproducible sin consultar este change
- [x] 4.2 Registrar en `README.md` la reversión manual de una publicación fallida (`git reset --hard` en la instancia y `docker compose up -d --build`) y el alcance del pipeline, dejando explícito que no hay rollback automático ni smoke tests
- [x] 4.3 Revisar `openspec/project.md` para que la sección «CI/CD con GitHub Actions» refleje el comando real de verificación del frontend y la ruta real del repositorio en la instancia; verificar que no queda ninguna referencia a un comando inexistente
- [x] 4.4 Comprobar que `.gitignore` sigue excluyendo `node_modules/` y que ninguna clave privada ni archivo de entorno con secretos aparece como archivo nuevo bajo control de versiones