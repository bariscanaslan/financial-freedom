#!/usr/bin/env sh
set -eu

: "${DEPLOY_ENV_FILE:?DEPLOY_ENV_FILE must be provided by Jenkins Secret file credentials}"

if [ ! -f "${DEPLOY_ENV_FILE}" ]; then
  echo "Jenkins production environment file does not exist: ${DEPLOY_ENV_FILE}" >&2
  exit 2
fi

# Dosya POSIX KEY=VALUE formatindadir. set -a ile Compose'un kullanacagi
# degerler de child process ortam degiskenlerine aktarilir.
set -a
. "${DEPLOY_ENV_FILE}"
set +a

: "${DEPLOY_DIR:?DEPLOY_DIR must be set in the Jenkins production environment file}"
: "${DEPLOY_PROJECT_NAME:=financial-freedom}"
: "${API_IMAGE:?API_IMAGE must be set}"
: "${UI_IMAGE:?UI_IMAGE must be set}"

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)

if [ ! -d "${DEPLOY_DIR}" ]; then
  echo "DEPLOY_DIR must exist: ${DEPLOY_DIR}" >&2
  exit 2
fi

# Jenkins container'i ile Docker host ayni mutlak DEPLOY_DIR yolunu gormelidir.
# Aksi halde bind mount'lar baska dizine gider ve canli veri gorunmez olur.
for directory in cache models portfolio_data nginx; do
  mkdir -p "${DEPLOY_DIR}/${directory}"
done

install -m 0644 "${ROOT}/compose.yaml" "${DEPLOY_DIR}/compose.yaml"
install -m 0644 "${ROOT}/compose.deploy.yaml" "${DEPLOY_DIR}/compose.deploy.yaml"
install -m 0644 "${ROOT}/nginx/default.conf" "${DEPLOY_DIR}/nginx/default.conf"
install -m 0600 "${DEPLOY_ENV_FILE}" "${DEPLOY_DIR}/.env"

compose() {
  docker compose \
    --project-name "${DEPLOY_PROJECT_NAME}" \
    --project-directory "${DEPLOY_DIR}" \
    --env-file "${DEPLOY_DIR}/.env" \
    -f "${DEPLOY_DIR}/compose.yaml" \
    -f "${DEPLOY_DIR}/compose.deploy.yaml" \
    "$@"
}

old_api=$(compose ps -q api 2>/dev/null || true)
old_ui=$(compose ps -q ui 2>/dev/null || true)
rollback_api=""
rollback_ui=""

if [ -n "${old_api}" ]; then
  rollback_api=$(docker inspect --format '{{.Image}}' "${old_api}")
fi
if [ -n "${old_ui}" ]; then
  rollback_ui=$(docker inspect --format '{{.Image}}' "${old_ui}")
fi

rollback() {
  if [ -n "${rollback_api}" ] && [ -n "${rollback_ui}" ]; then
    echo "Health check failed; restoring previous images." >&2
    API_IMAGE="${rollback_api}" UI_IMAGE="${rollback_ui}" compose up -d --no-build
  fi
}
trap rollback HUP INT TERM

if ! compose up -d --no-build --wait --wait-timeout 240; then
  rollback
  exit 1
fi

# Docker health durumuna ek olarak nginx -> api proxy yolunu da dogrula.
if ! compose exec -T nginx wget -qO- http://127.0.0.1/api/health >/dev/null; then
  rollback
  exit 1
fi

trap - HUP INT TERM
compose ps
