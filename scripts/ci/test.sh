#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
RESULTS_DIR="${ROOT}/test-results"

rm -rf "${RESULTS_DIR}"
mkdir -p "${RESULTS_DIR}/backend" "${RESULTS_DIR}/frontend"

docker build \
  --target test-results \
  --output "type=local,dest=${RESULTS_DIR}/backend" \
  -f "${ROOT}/Dockerfile" \
  "${ROOT}"

docker build \
  --target test-results \
  --output "type=local,dest=${RESULTS_DIR}/frontend" \
  -f "${ROOT}/ui/Dockerfile" \
  "${ROOT}/ui"

# Production derlemeleri de CI kalite kapisidir. Testten sonra ayni commit'in
# gercek runtime image'lari uretilir; deploy asamasi bunlari yeniden derlemez.
docker build --target runtime -t "${API_IMAGE:?API_IMAGE must be set}" -f "${ROOT}/Dockerfile" "${ROOT}"
docker build --target runner -t "${UI_IMAGE:?UI_IMAGE must be set}" -f "${ROOT}/ui/Dockerfile" "${ROOT}/ui"
