#!/usr/bin/env bash
set -euo pipefail

# === Configura esto una vez ===
PROJECT_ID="llm-router-project-479922"
REGION="us-central1"
REPO="llm-router-repo"  # Artifact Registry repo name
AR_HOST="${REGION}-docker.pkg.dev"

ROUTER_SERVICE="llm-router"
CLASSIFIER_SERVICE="llm-classifier"

ROUTER_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/${ROUTER_SERVICE}"
CLASSIFIER_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/${CLASSIFIER_SERVICE}"

# Paths (asumiendo estructura /router y /classifier)
ROUTER_DIR="router"
CLASSIFIER_DIR="classifier"

# Endpoint del classifier (se rellenará después del deploy)
CLASSIFIER_PREDICT_PATH="/predict"

# Secret name (Secret Manager)
GEMINI_SECRET_NAME="GEMINI_API_KEY"
GEMINI_SECRET_VERSION="latest"

# === Helpers ===
tag() {
  # tag con fecha+git sha corto si existe
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  local sha="nogit"
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    sha="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
  fi
  echo "${ts}-${sha}"
}

ensure_project_region() {
  gcloud config set project "${PROJECT_ID}" >/dev/null
  gcloud config set run/region "${REGION}" >/dev/null
}

build_and_push() {
  local service="$1"
  local dir="$2"
  local image="$3"
  local version="$4"

  echo "==> Build & push: ${service} (${dir}) -> ${image}:${version}"
  gcloud builds submit --region "${REGION}" --tag "${image}:${version}" "${dir}"
}

deploy_service() {
  local service="$1"
  local image="$2"
  local version="$3"

  echo "==> Deploy: ${service} -> ${image}:${version}"
  gcloud run deploy "${service}" \
    --image "${image}:${version}" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated
}

get_service_url() {
  local service="$1"
  gcloud run services describe "${service}" --region "${REGION}" --format="value(status.url)"
}

set_router_envs() {
  local classifier_url="$1"

  echo "==> Set router env: CLASSIFIER_URL=${classifier_url}${CLASSIFIER_PREDICT_PATH}"
  gcloud run services update "${ROUTER_SERVICE}" \
    --region "${REGION}" \
    --set-env-vars "CLASSIFIER_URL=${classifier_url}${CLASSIFIER_PREDICT_PATH}"
}

inject_gemini_secret() {
  echo "==> Inject secret into router: ${GEMINI_SECRET_NAME}:${GEMINI_SECRET_VERSION}"
  gcloud run services update "${ROUTER_SERVICE}" \
    --region "${REGION}" \
    --update-secrets "${GEMINI_SECRET_NAME}=${GEMINI_SECRET_NAME}:${GEMINI_SECRET_VERSION}"
}

smoke_tests() {
  local router_url="$1"
  local classifier_url="$2"

  echo "==> Smoke: classifier /health"
curl -fsS "${router_url}/health" >/dev/null
  echo "==> Smoke: router /health"
  curl -fsS "${router_url}/health" >/dev/null && echo "OK"

  echo "==> Smoke: classifier /predict"
  curl -fsS -X POST "${classifier_url}${CLASSIFIER_PREDICT_PATH}" \
    -H "Content-Type: application/json" \
    -d '{"text":"Define API con ejemplo","metadata":{}}' >/dev/null && echo "OK"

  echo "==> Smoke: router /route"
  curl -fsS -X POST "${router_url}/route" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"u1","text":"Define qué es una API con ejemplo"}' | head -c 400; echo
}

main() {
  ensure_project_region

  local version
  version="$(tag)"
  echo "==> Version tag: ${version}"

  # 1) Build & deploy classifier primero (router depende de su URL)
  build_and_push "${CLASSIFIER_SERVICE}" "${CLASSIFIER_DIR}" "${CLASSIFIER_IMAGE}" "${version}"
  deploy_service "${CLASSIFIER_SERVICE}" "${CLASSIFIER_IMAGE}" "${version}"

  local classifier_url
  classifier_url="$(get_service_url "${CLASSIFIER_SERVICE}")"
  echo "Classifier URL: ${classifier_url}"

  # 2) Build & deploy router
  build_and_push "${ROUTER_SERVICE}" "${ROUTER_DIR}" "${ROUTER_IMAGE}" "${version}"
  deploy_service "${ROUTER_SERVICE}" "${ROUTER_IMAGE}" "${version}"

  local router_url
  router_url="$(get_service_url "${ROUTER_SERVICE}")"
  echo "Router URL: ${router_url}"

  # 3) Set env vars + secrets (no rebuild)
  set_router_envs "${classifier_url}"
  inject_gemini_secret

  # 4) Smoke tests
  smoke_tests "${router_url}" "${classifier_url}"

  echo
  echo "DONE ✅"
  echo "Router:     ${router_url}"
  echo "Classifier: ${classifier_url}"
}

main "$@"
