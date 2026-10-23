#!/usr/bin/env bash
# Email alert when a crawl market fails (see crawler/main.py: the run exits
# non-zero and logs "market(s) failed: <brand / url -> error>" at ERROR).
#
# Creates, idempotently, through the Cloud Monitoring REST API (so only the
# core gcloud SDK is needed, no alpha/beta components):
#   1. an email notification channel
#   2. a log-based alert policy that emails the matching log entry (which
#      carries the failed markets and their errors) to that address
#
# Usage:
#   PROJECT_ID=soeur-shopify-tracker ALERT_EMAIL=hugo.albert.marques@gmail.com ./deploy/alerting.sh
#
# Set GCLOUD to the gcloud binary if it is not on PATH.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. soeur-shopify-tracker}"
ALERT_EMAIL="${ALERT_EMAIL:?Set ALERT_EMAIL}"
JOB_NAME="${JOB_NAME:-shopify-tracker}"
GCLOUD="${GCLOUD:-gcloud}"
POLICY_NAME="shopify-tracker: marché en échec"
API="https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}"
TEMPLATE="$(cd "$(dirname "$0")" && pwd)/alert_policy.json"

TOKEN="$("$GCLOUD" auth print-access-token)"
AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")

# Reads one JSON field from stdin: json_get <dotted.path>
json_get() {
  python3 -c '
import json, sys
value = json.load(sys.stdin)
for key in sys.argv[1].split("."):
    value = value.get(key, []) if isinstance(value, dict) else []
if isinstance(value, list):
    print(value[0]["name"] if value else "")
else:
    print(value)
' "$1"
}

echo "== Notification channel =="
CHANNEL="$(curl -sf -G "${AUTH[@]}" "${API}/notificationChannels" \
  --data-urlencode "filter=type=\"email\" AND labels.email_address=\"${ALERT_EMAIL}\"" \
  | json_get notificationChannels)"
if [ -z "$CHANNEL" ]; then
  CHANNEL="$(curl -sf -X POST "${AUTH[@]}" "${API}/notificationChannels" \
    -d "{\"type\":\"email\",\"displayName\":\"shopify-tracker ${ALERT_EMAIL}\",\"labels\":{\"email_address\":\"${ALERT_EMAIL}\"}}" \
    | json_get name)"
  echo "created ${CHANNEL}"
else
  echo "exists ${CHANNEL}"
fi

echo "== Alert policy =="
EXISTING="$(curl -sf -G "${AUTH[@]}" "${API}/alertPolicies" \
  --data-urlencode "filter=display_name=\"${POLICY_NAME}\"" \
  | json_get alertPolicies)"
if [ -n "$EXISTING" ]; then
  echo "exists ${EXISTING} (delete it in the console to recreate it from deploy/alert_policy.json)"
  exit 0
fi

POLICY_FILE="$(mktemp)"
trap 'rm -f "$POLICY_FILE"' EXIT
sed -e "s|__JOB_NAME__|${JOB_NAME}|g" -e "s|__CHANNEL__|${CHANNEL}|g" "$TEMPLATE" > "$POLICY_FILE"
curl -sf -X POST "${AUTH[@]}" "${API}/alertPolicies" --data-binary "@${POLICY_FILE}" \
  | json_get name
echo "Done."
