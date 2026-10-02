# Design

## Context

Ver la justificación en `proposal.md` y el contrato de comportamiento en
`specs/ci-cd/spec.md`. Esta sección recoge sólo las restricciones del estado actual que
condicionan el diseño.

- El proyecto ya está en un repositorio de GitHub (`J0sePs/app-2-weather`) con
  `main` como rama de publicación, y no tiene aún directorio `.github/`.
- `backend/uv.lock` y `frontend/package-lock.json` están versionados, así que
  `--frozen` y `npm ci` resuelven de forma reproducible sin trabajo adicional.
- La configuración de pruebas del backend ya está en
  `backend/pyproject.toml`: `testpaths = ["tests"]` y
  `addopts = "--cov=app --cov-fail-under=80"`. El umbral de cobertura no hay que
  reintroducirlo en el workflow; basta ejecutar la suite desde la raíz del backend.
- `frontend/package.json` sólo declara `test: ng test`. No existe `test:ci`, y `ng test`
  arranca Karma en modo interactivo (`watch`), que en un runner no termina nunca.
- El frontend usa el constructor `@angular/build:karma` con `karma-coverage` y
  `karma-chrome-launcher`, sin `karma.conf.js`. El constructor acepta las opciones
  `watch` y `browsers`, de modo que ambos flags se pueden pasar por línea de órdenes.
- `infra/terraform/user_data.sh` deja el repositorio clonado en
  `/home/ec2-user/app-2-weather`, propiedad de `ec2-user`, con el usuario ya miembro del
  grupo `docker` y un intercambio de 2 GB activo. El `git pull` del despliegue depende de
  esa propiedad y de ese permiso.
- La instancia es `t3.micro` con 1 GB de RAM. El presupuesto de runtime del conjunto es
  < 400 MB, pero el *build* multietapa del frontend es lo que no cabe en memoria.
- La clave privada `app2w-deploy` existe en la máquina del operador y su mitad pública
  está registrada en AWS por Terraform. Es el mismo material que consumirá el pipeline.

## Goals / Non-Goals

**Goals:**

- Un único fichero de workflow que describa los tres trabajos y su orden de dependencia.
- Que el despliegue no pueda ocurrir sin que backend y frontend pasen sus pruebas y sin
  que una persona lo apruebe.
- Que el runner no requiera ninguna credencial: los tres trabajos de prueba corren sin
  secretos.
- Que el script remoto sea el mínimo imprescindible, con los cinco pasos de
  `project.md` y nada más.

**Non-Goals:**

- Sustituir al CI de Terraform: no hay `plan` ni `apply` en el pipeline. La
  infraestructura sólo cambia a mano con `terraform apply`.
- Publicar imágenes en GHCR, como ya está declarado en los non-goals de `project.md`.
- Rollback automático, ni *smoke tests* posteriores al despliegue.
- Matrices de versión (varios Python o varios Node) y pruebas de navegador cruzadas.
- Mecanismo de caché propio: el de `npm` es el integrado en `setup-node`, y el de `uv` el
  integrado en `setup-uv`. No hay directorios de caché manuales ni claves de
  `actions/cache` añadidas al flujo.
- Cualquier cambio en `containerized-deployment` o `infrastructure-as-code`: el pipeline
  sólo invoca `docker compose up -d --build` sobre lo que ya está definido.

## Decisions

### Un solo fichero de workflow, no uno por etapa

Los tres trabajos comparten disparadores, versión de Actions y política de permisos;
separarlos en `ci.yml` y `cd.yml` duplicaría el bloque `on:` y obligaría a coordinar
`workflow_run` para encadenar el despliegue, que es un patrón frágil y con peor
diagnóstico. Con un fichero, la dependencia `needs:` es explícita y legible en pantalla.

*Alternativa considerada:* un `ci.yml` que dispare por `workflow_run` al terminar, y un
`cd.yml` aparte. Descartada porque `workflow_run` ejecuta con privilegios del
disparador original y complicate el manejo de aprobación.

### Despliegue por SSH en lugar de runner self-hosted o CodeDeploy

La instancia ya está preparada por `user_data.sh` con Docker, Compose v2, git y el
permiso de usuario. `appleboy/ssh-action` es el único añadido: no hay que instalar un
agente que quede corriendo en la instancia ni registrar credenciales de AWS en el
pipeline, y el material de acceso es el mismo que Terraform ya registró.

*Alternativas consideradas:*

- *Runner self-hosted* etiquetado `production`: exige que la instancia esté encendida y
  con el agente registrado para que cualquier push se pueda verificar, y ese agente es
  una nueva superficie de ataque permanente en una máquina con puerto 22 abierto a una
  IP.
- *CodeDeploy* de AWS: requiere instalar el agente, dar permisos IAM a la instancia y
  mantener una aplicación y un rol más, para un despliegue de cinco comandos.

### Construir en la EC2 en lugar de construir en el runner y publicar en un registro

El intercambio de 2 GB que instaló `user_data.sh` existe exactamente para esto, y el
proyecto ya decidió no usar GHCR. La contrapartida es que el build del frontend tarda
varios minutos en una `t3.micro` y que un fallo de build aparece en el momento del
despliegue y no en el de pruebas. Se acepta: el presupuesto es de una instancia, y
mantener un registro añadiría autenticación, disco y un paso de caché que no aporta nada
al resultado visible.

### `test:ci` declarado en `package.json`

Se añade `"test:ci": "ng test --watch=false --browsers=ChromeHeadless"` al manifiesto del
frontend y el workflow invoca `npm run test:ci`. Declarar el comando en el proyecto, y no
como banderas sueltas en el workflow, mantiene la definición de "cómo se verifican las
pruebas" dentro del frontend: el mismo comando sirve en local y en el pipeline, y `main`
coincide con lo que `project.md` documenta.

*Alternativa considerada:* `npx ng test --watch=false --browsers=ChromeHeadless` en el
workflow, sin tocar el manifiesto. Es un fichero menos, pero deja `project.md`
desincronizado y hace que el modo interactivo sea el único modo documentado del proyecto.

### Chrome instalado explícitamente en el runner

Karma necesita un binario de Chrome. Las imágenes `ubuntu-22.04` de los runners
alojados no lo garantizan, así que el trabajo usa `browser-actions/setup-chrome@v1` en
lugar de confiar en la imagen. Sin `--no-sandbox`: en un runner alojado las espacios de
nombres de usuario están disponibles y Chrome headless arranca con su sandbox. El
lanzador `ChromeHeadless` lo provee `karma-chrome-launcher`, que ya es dependencia de
desarrollo.

### Permisos mínimos y concurrencia por referencia

El workflow declara `permissions: contents: read` en el ámbito superior, de modo que el
token de `GITHUB_TOKEN` no hereda permisos de escritura que ningún trabajo necesita.

Se declara `concurrency` por referencia con cancelación únicamente fuera de `main`: así
dos pushes a `main` pueden convivir —el segundo no interrumpe un despliegue que ya está a
la espera de aprobación— mientras que las ejecuciones de pull requests obsoletas sí se
cancelan solas y no gastan minutos de runner.

### `set -e` y los cinco pasos, sin más

El script remoto es literalmente la secuencia de `project.md`. El primer `set -e` hace que
un fallo intermedio no continúe hasta un paso que depende de él. `docker image prune -f`
sin `-a` sólo elimina imágenes colgantes, que es lo que deja una reconstrucción; con `-a`
se borraría caché que la siguiente publicación reutiliza. No se añade `docker compose
pull` porque no hay registro del que traer. No se usa `sudo`: el usuario de la instancia ya
está en el grupo `docker`.

## Risks / Trade-offs

- **[El build en la `t3.micro` es lento y puede agotar la memoria]** → El intercambio de 2 GB ya está
  activo y persistente por `user_data.sh`, que es lo que convierte un OOM en lentitud. Se
  fija un `timeout-minutes` holgado en el trabajo de despliegue para que un build lento
  no se interprete como un fallo, y el `git pull` ocurre antes de construir, de modo que
  un fallo de red se distingue de un fallo de build en el propio registro.
- **[Chrome headless puede no arrancar por el sandbox]** → Si aparece, el arreglo es un
  `karma.conf.js` mínimo con un lanzador personalizado `ChromeHeadlessNoSandbox` y la
  opción `karmaConfig` correspondiente en `angular.json`, más `--browsers=ChromeHeadlessNoSandbox`
  en `test:ci`. Es un cambio de tres puntos y no altera el contrato de la especificación.
- **[La clave privada de despliegue queda almacenada en GitHub]** → Es el mismo material
  cuya mitad pública Terraform ya registró en AWS, y no se versiona en el repositorio. El
  riesgo real es que el secreto conviva en dos sistemas; la rotación consiste en
  reregistrar el par en Terraform y reemplazar el secreto del entorno, que es el mismo
  procedimiento en ambos lados.
- **[Un despliegue aprobado no se puede deshacer automáticamente]** → Declarado en los
  non-goals de `project.md`. La reversión es manual: `git reset --hard` en la instancia y
  `docker compose up -d --build`. Mientras tanto, un despliegue fallido deja los
  contenedores anteriores en ejecución, porque `up -d` no borra el servicio que no se
  reconstruye con éxito.
- **[Dependencia de acciones de terceros en el camino de despliegue]** → Todas se fijan
  por versión, nunca por rama. Es una dependencia asumida del enfoque; la alternativa
  (escribir el despliegue con `ssh` del propio runner y `rsync`) elimina la acción a costa
  de reimplementar la gestión de la clave y del `known_hosts` a mano.
- **[Sin verificación posterior al despliegue]** → Declarado en los non-goals. El
  despliegue se considera correcto cuando el script termina con código cero, que es
  exactamente la garantía que da `set -e`. La comprobación de salud es manual hasta que
  se añada smoke tests.

## Migration Plan

1. Crear en GitHub el entorno `production` (Settings → Environments) con la regla de
   revisores requeridos activa y al menos un revisor.
2. Añadir los secretos del entorno: `EC2_HOST` con la salida `instance_public_ip` de
   `terraform output`, `EC2_USER` con `ec2-user` y `EC2_SSH_KEY` con el contenido íntegro
   de `~/.ssh/app2w-deploy`.
3. Confirmar el nuevo script `test:ci` junto con el workflow, sin publicar todavía: una
   pull request de prueba valida los dos trabajos de prueba sin tocar la instancia.
4. Fusionar en `main` y aprobar la ejecución del trabajo de despliegue.

**Reversión:** eliminar el fichero `.github/workflows/ci-cd.yml` devuelve el repositorio
al estado previo, porque nada más del proyecto depende del pipeline. Volver atrás una
publicación ya realizada es manual, según la sección de riesgos.

## Open Questions

Ninguna. Las decisiones que quedaba abiertas —cómo se invoca la suite del frontend sin
bloquear el runner y si se toca el manifiesto del proyecto para ello— se resolvieron antes
de redactar este diseño.