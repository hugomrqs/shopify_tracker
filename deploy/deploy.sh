#!/usr/bin/env bash
# One-shot setup: new GCP project, Firestore, Artifact Registry, Cloud Run Job,
# and a Cloud Scheduler trigger. Idempotent-ish (safe to re-run), but review
# before running against an existing project.
#
# Prerequisites (manual, interactive — cannot be scripted):
#   gcloud auth login
#   gcloud auth application-default login   # only needed for local runs of crawler/main.py
#
# Usage:
#   PROJECT_ID=soeur-shopify-tracker BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX ./deploy.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. soeur-shopify-tracker}"
BILLING_ACCOUNT_ID="${BILLING_ACCOUNT_ID:?Set BILLING_ACCOUNT_ID (run: gcloud billing accounts list)}"
REGION="${REGION:-europe-west1}"
JOB_NAME="${JOB_NAME:-shopify-tracker}"
REPO_NAME="${REPO_NAME:-shopify-tracker}"
SCHEDULE="${SCHEDULE:-0 6 * * *}"        # daily at 06:00
SCHEDULER_SA="scheduler-${JOB_NAME}"
RUNTIME_SA="runtime-${JOB_NAME}"

echo "== Project =="
if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud projects create "$PROJECT_ID"
fi
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
gcloud config set project "$PROJECT_ID"

echo "== APIs =="
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com

echo "== Firestore (native mode) =="
gcloud firestore databases create --location="$REGION" || echo "Firestore database already exists, skipping"

echo "== Artifact Registry =="
gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Shopify tracker crawler images" \
  || echo "Repo already exists, skipping"

echo "== Build & push image =="
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${JOB_NAME}:latest"
gcloud builds submit --tag "$IMAGE" ..

echo "== Runtime service account (Firestore write access) =="
gcloud iam service-accounts create "$RUNTIME_SA" --display-name="Shopify tracker runtime" \
  || echo "SA already exists, skipping"
RUNTIME_SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role="roles/datastore.user" \
  --condition=None

echo "== Cloud Run Job =="
gcloud run jobs describe "$JOB_NAME" --region="$REGION" >/dev/null 2>&1 && ACTION=update || ACTION=create
gcloud run jobs "$ACTION" "$JOB_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA_EMAIL" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --max-retries=1 \
  --task-timeout=1800

echo "== Scheduler service account (permission to run the job) =="
gcloud iam service-accounts create "$SCHEDULER_SA" --display-name="Shopify tracker scheduler" \
  || echo "SA already exists, skipping"
SCHEDULER_SA_EMAIL="${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --region="$REGION" \
  --member="serviceAccount:${SCHEDULER_SA_EMAIL}" \
  --role="roles/run.invoker"

echo "== Cloud Scheduler =="
gcloud scheduler jobs describe "$JOB_NAME" --location="$REGION" >/dev/null 2>&1 && SACTION=update || SACTION=create
gcloud scheduler jobs "$SACTION" http "$JOB_NAME" \
  --location="$REGION" \
  --schedule="$SCHEDULE" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"

echo "Done. Trigger a manual run with:"
echo "  gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
