#!/usr/bin/env bash
# Roll a Lightsail container service back to a previous deployment version.
#
# Usage:
#   scripts/lightsail_rollback.sh <service-name> [version]
#
# With no version, rolls back to the most recent *successful* deployment older
# than the current one (skipping FAILED versions). With a version number, rolls
# back to exactly that version.
#
#   scripts/lightsail_rollback.sh hablemos-discordpy-bot        # previous good version
#   scripts/lightsail_rollback.sh hablemos-activity 3           # specific version
#
# Requires: aws v2, python3, valid AWS creds. Region via AWS_REGION (default us-east-1).
#
# How it works: Lightsail stores each past deployment's full spec (containers +
# publicEndpoint). We fetch the target version's spec and re-submit it as a new
# deployment. The image ref (e.g. :service.app.7) is preserved, so no rebuild.

set -euo pipefail

SERVICE="${1:?service name required}"
TARGET_VERSION="${2:-}"
REGION="${AWS_REGION:-us-east-1}"

# Pick target version and extract containers + optional publicEndpoint into temp files.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Write the deployments listing to a file so Python reads it robustly (env
# values may contain quotes/newlines that would break heredoc interpolation).
aws lightsail get-container-service-deployments \
  --region "$REGION" --service-name "$SERVICE" --output json > "$WORK/deployments.json"

RESOLVED_VERSION="$(TARGET="$TARGET_VERSION" WORK="$WORK" python3 <<'PY'
import os, json
work = os.environ["WORK"]
with open(os.path.join(work, "deployments.json")) as f:
    deployments = json.load(f)["deployments"]
target = os.environ.get("TARGET", "").strip()

# Sort newest-first (API already does, but be safe).
deployments.sort(key=lambda d: d["version"], reverse=True)

chosen = None
if target:
    for d in deployments:
        if str(d["version"]) == target:
            chosen = d
            break
    if chosen is None:
        raise SystemExit(f"ERROR: version {target} not found")
    if chosen["state"] == "FAILED":
        raise SystemExit(f"ERROR: version {target} is FAILED — refusing to roll back to it")
else:
    # Most recent successful version that is NOT the current active one.
    # deployments[0] is current; find the next ACTIVE/INACTIVE (successful) below it.
    current = deployments[0]["version"] if deployments else None
    for d in deployments[1:]:
        if d["state"] in ("ACTIVE", "INACTIVE"):  # both mean it deployed successfully at some point
            chosen = d
            break
    if chosen is None:
        raise SystemExit("ERROR: no previous successful deployment to roll back to")

with open(os.path.join(work, "containers.json"), "w") as f:
    json.dump(chosen["containers"], f)

pe = chosen.get("publicEndpoint")
if pe:
    # Reshape into the create-deployment --public-endpoint format.
    ep = {"containerName": pe["containerName"], "containerPort": pe["containerPort"]}
    if pe.get("healthCheck"):
        ep["healthCheck"] = pe["healthCheck"]
    with open(os.path.join(work, "endpoint.json"), "w") as f:
        json.dump(ep, f)

print(chosen["version"])
PY
)"

echo "==> Rolling $SERVICE back to deployment version $RESOLVED_VERSION"

DEPLOY_ARGS=(--region "$REGION" --service-name "$SERVICE" --containers "file://$WORK/containers.json")
if [ -f "$WORK/endpoint.json" ]; then
  DEPLOY_ARGS+=(--public-endpoint "file://$WORK/endpoint.json")
fi

aws lightsail create-container-service-deployment "${DEPLOY_ARGS[@]}" >/dev/null

NEW_VERSION="$(aws lightsail get-container-service-deployments --region "$REGION" --service-name "$SERVICE" \
  --query 'deployments[0].version' --output text)"
echo "==> Submitted new deployment v$NEW_VERSION (a copy of v$RESOLVED_VERSION). Polling until ACTIVE..."

for i in $(seq 1 40); do
  STATE="$(aws lightsail get-container-service-deployments --region "$REGION" --service-name "$SERVICE" \
    --query "deployments[?version==\`$NEW_VERSION\`].state | [0]" --output text 2>/dev/null || echo "PENDING")"
  echo "  [$i] v$NEW_VERSION state=$STATE"
  case "$STATE" in
    ACTIVE) echo "==> Rollback complete: $SERVICE now on v$NEW_VERSION"; exit 0 ;;
    FAILED|INACTIVE)
      echo "ERROR: rollback deployment ended in $STATE" >&2
      aws lightsail get-container-log --region "$REGION" --service-name "$SERVICE" \
        --container-name app --query 'logEvents[-20:].message' --output text 2>/dev/null >&2 || true
      exit 1 ;;
  esac
  sleep 10
done

echo "ERROR: timed out waiting for rollback to become ACTIVE" >&2
exit 1
