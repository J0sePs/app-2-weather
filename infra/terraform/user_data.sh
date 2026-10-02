#!/bin/bash
#
# Arranque de la instancia EC2 del predictor de Machu Picchu.
#
# cloud-init ejecuta este script una sola vez, en el primer arranque de la instancia que
# crea `terraform apply`. Deja el host preparado para que desplegar la aplicación sea un
# `docker compose up -d --build`, sin pasos manuales.
#
# El script es idempotente a propósito: si se relanza a mano (por SSH o desde
# cloud-init) no debe fallar ni dejar el host incoherente. Por eso la instalación de
# paquetes, el alta en el grupo `docker`, la línea de `/etc/fstab` y la marca de fin
# están todas protegidas por condiciones.

set -euo pipefail

REPO_URL="https://github.com/J0sePs/app-2-weather.git"
REPO_DIR="/home/ec2-user/app-2-weather"
COMPOSE_PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"
COMPOSE_VERSION="v2.29.7"
SWAP_FILE="/swapfile"
SWAP_SIZE_MB=2048
DONE_MARKER="/tmp/bootstrap-done"

log() {
  echo "[bootstrap] $*"
}

# ---------------------------------------------------------------------------
# 1. Sistema actualizado y cliente de Git
# ---------------------------------------------------------------------------
log "Actualizando el sistema"
dnf update -y

log "Instalando git"
dnf install -y git

# ----------------------------------------------------------------------------
# 2. Docker desde los repositorios de Amazon Linux 2023
#
# AL2023 incluye Docker en sus propios repos (sin plugin de Compose, que se
# instala como binario en el paso 3). No se usa el repo oficial de Docker
# porque no existe para Amazon Linux.
# ----------------------------------------------------------------------------
log "Instalando Docker desde los repositorios de Amazon Linux"
dnf install -y docker

# ---------------------------------------------------------------------------
# 3. Complemento Docker Compose v2
#
# Se baja el binario oficial porque el repositorio anterior no incluye `docker-compose-
# plugin` como paquete en Amazon Linux 2023. `chmod +x` es obligatorio: el binario no lo
# trae tras descomprimir.
# ---------------------------------------------------------------------------
log "Instalando el complemento de Docker Compose v2 (${COMPOSE_VERSION})"
install -m 0755 -d "${COMPOSE_PLUGIN_DIR}"
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o "${COMPOSE_PLUGIN_DIR}/docker-compose"
chmod +x "${COMPOSE_PLUGIN_DIR}/docker-compose"

# ---------------------------------------------------------------------------
# 4. Motor de contenedores en ejecución y permiso para el usuario de la instancia
# ---------------------------------------------------------------------------
log "Habilitando e iniciando Docker"
systemctl enable --now docker

# `getent group docker` evita el error de "group already exists" al relanzar el script.
if ! getent group docker >/dev/null; then
  groupadd docker
fi
if ! id -nG ec2-user | tr ' ' '\n' | grep -qx docker; then
  log "Añadiendo ec2-user al grupo docker"
  usermod -aG docker ec2-user
fi

# ---------------------------------------------------------------------------
# 5. Swap de 2 GB, activado y persistente
#
# La instancia es t3.micro (1 GB de RAM) y el presupuesto de runtime es < 400 MB. Lo que
# se queda sin memoria es el build multietapa del frontend, no el runtime; el swap
# convierte ese OOM en lentitud. La línea de /etc/fstab se protege con grep -q para no
# duplicarla al relanzar el script.
# ---------------------------------------------------------------------------
if [ ! -f "${SWAP_FILE}" ]; then
  log "Creando el swap de ${SWAP_SIZE_MB} MB en ${SWAP_FILE}"
  fallocate -l "${SWAP_SIZE_MB}M" "${SWAP_FILE}"
  chmod 600 "${SWAP_FILE}"
  mkswap "${SWAP_FILE}" >/dev/null
  swapon "${SWAP_FILE}"
else
  log "El swap ya existe; sólo se activa y persiste"
  swapon "${SWAP_FILE}" 2>/dev/null || true
fi

if ! grep -q "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
  echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
  log "Swap persistido en /etc/fstab"
fi

# ---------------------------------------------------------------------------
# 6. Clon del repositorio como ec2-user
#
# Como `ec2-user` y no como root: un directorio con propiedad de root rompe el `git pull`
# que hace el pipeline por SSH.
# ---------------------------------------------------------------------------
if [ -d "${REPO_DIR}/.git" ]; then
  log "El repositorio ya está clonado en ${REPO_DIR}"
else
  log "Clonando ${REPO_URL} en ${REPO_DIR}"
  rm -rf "${REPO_DIR}"
  su - ec2-user -c "git clone ${REPO_URL} ${REPO_DIR}"
fi

# ---------------------------------------------------------------------------
# 7. Marca de fin de arranque
#
# Su ausencia es la señal de que el arranque se quedó a medias; el README la usa como
# comprobación de salud del arranque.
# ---------------------------------------------------------------------------
touch "${DONE_MARKER}"
log "Arranque completado"

