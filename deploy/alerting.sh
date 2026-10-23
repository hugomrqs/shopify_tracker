#!/usr/bin/env bash
# Email alert when a crawl market fails (see crawler/main.py: the run exits
# non-zero and logs "market(s) failed: <brand / url -> error>" at ERROR).
#
# Creates, idempotently:
#   1. an email notification channel
#   2. a log-based alert policy that emails the matching log entry (which
#      carries the failed markets and their errors) to that address
#
# Usage:
#   PROJECT_ID=soeur-shopify-tracker ALERT_EMAIL=hugo.albert.marques@gmail.com ./deploy/alerting.sh
#
# Requires the gcloud alpha/beta components (gcloud components install alpha beta).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. soeur-shopify-tracker}"
ALERT_EMAIL="${ALERT_EMAIL:?Set ALERT_EMAIL}"
JOB_NAME="${JOB_NAME:-shopify-tracker}"
POLICY_NAME="shopify-tracker: marché en échec"
TEMPLATE="$(cd "$(dirname "$0")" && pwd)/alert_policy.json"

echo "== Notification channel =="
CHANNEL="$(gcloud beta monitoring channels list --project="$PROJECT_ID" \
  --filter="type=\"email\" AND labels.email_address=\"${ALERT_EMAIL}\"" \
  --format="value(name)" | head -n1)"
if [ -z "$CHANNEL" ]; then
  CHANNEL="$(gcloud beta monitoring channels create --project="$PROJECT_ID" \
    --display-name="shopify-tracker ${ALERT_EMAIL}" \
    --type=email \
    --channel-labels="email_address=${ALERT_EMAIL}" \
    --format="value(name)")"
  echo "created $CHANNEL"
else
  echo "exists $CHANNEL"
fi

echo "== Alert policy =="
EXISTING="$(gcloud alpha monitoring policies list --project="$PROJECT_ID" \
  --filter="displayName=\"${POLICY_NAME}\"" --format="value(name)" | head -n1)"
if [ -n "$EXISTING" ]; then
  echo "exists $EXISTING (delete it in the console to recreate it from deploy/alert_policy.json)"
  exit 0
fi

POLICY_FILE="$(mktemp)"
trap 'rm -f "$POLICY_FILE"' EXIT
sed -e "s|__JOB_NAME__|${JOB_NAME}|g" -e "s|__CHANNEL__|${CHANNEL}|g" "$TEMPLATE" > "$POLICY_FILE"
gcloud alpha monitoring policies create --project="$PROJECT_ID" --policy-from-file="$POLICY_FILE"
echo "Done. Send a test: run a job whose market fails, or wait for the next failing daily run."
