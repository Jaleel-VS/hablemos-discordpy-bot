#!/usr/bin/env bash
# Push a built image to a Lightsail container service and create a deployment.
#
# Usage:
#   scripts/lightsail_deploy.sh <service-name> <local-image-tag> <containers-json> [public-endpoint-json]
#
# Requires on PATH: aws (v2), lightsailctl, docker (image already built/tagged).
# Requires env: AWS_REGION (defaults to us-east-1).
#
# The containers-json / public-endpoint-json files may contain the literal
# placeholder __IMAGE__ which is replaced with the Lightsail image ref that
# push-container-image returns (e.g. :hablemos-activity.app.7).

set -euo pipefail

SERVICE="${1:?service name required}"
LOCAL_IMAGE="${2:?local image tag required}"
CONTAINERS_JSON="${3:?containers json path required}"
ENDPOINT_JSON="${4:-}"
REGION="${AWS_REGION:-us-east-1}"

echo "==> Pushing $LOCAL_IMAGE to service $SERVICE ($REGION)"
PUSH_OUT="$(aws lightsail push-container-image \
  --region "$REGION" \
  --service-name "$SERVICE" \
  --label app \
  --image "$LOCAL_IMAGE" 2>&1)"
echo "$PUSH_OUT"

# Parse the "Refer to this image as ":service.app.N"" line.
IMAGE_REF="$(printf '%s\n' "$PUSH_OUT" | sed -n 's/.*Refer to this image as "\(:[^"]*\)".*/\1/p' | tail -1)"
if [ -z "$IMAGE_REF" ]; then
  echo "ERROR: could not determine pushed image ref from push output" >&2
  exit 1
fi
echo "==> Pushed image ref: $IMAGE_REF"

# Substitute __IMAGE__ into a temp copy of the container config.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CONTAINERS_RESOLVED="$WORK/containers.json"
sed "s|__IMAGE__|$IMAGE_REF|g" "$CONTAINERS_JSON" > "$CONTAINERS_RESOLVED"

DEPLOY_ARGS=(--region "$REGION" --service-name "$SERVICE" --containers "file://$CONTAINERS_RESOLVED")
if [ -n "$ENDPOINT_JSON" ]; then
  DEPLOY_ARGS+=(--public-endpoint "file://$ENDPOINT_JSON")
fi

echo "==> Creating deployment for $SERVICE"
aws lightsail create-container-service-deployment "${DEPLOY_ARGS[@]}" >/dev/null

# Capture the version number of the deployment we just created. deployments[0]
# is the newest. We must track THIS version, not currentDeployment.state —
# currentDeployment keeps pointing at the old (healthy) version until the new
# one succeeds, so polling it gives a false pass when a new deploy is failing.
NEW_VERSION="$(aws lightsail get-container-service-deployments --region "$REGION" --service-name "$SERVICE" \
  --query 'deployments[0].version' --output text 2>/dev/null)"
echo "==> Submitted deployment version $NEW_VERSION. Polling until it is ACTIVE..."

for i in $(seq 1 40); do
  STATE="$(aws lightsail get-container-service-deployments --region "$REGION" --service-name "$SERVICE" \
    --query "deployments[?version==\`$NEW_VERSION\`].state | [0]" --output text 2>/dev/null || echo "PENDING")"
  echo "  [$i] deployment v$NEW_VERSION state=$STATE"
  case "$STATE" in
    ACTIVE)
      echo "==> $SERVICE deployment v$NEW_VERSION is ACTIVE"
      exit 0 ;;
    FAILED|INACTIVE)
      echo "ERROR: deployment v$NEW_VERSION ended in state $STATE" >&2
      echo "--- recent container logs ---" >&2
      aws lightsail get-container-log --region "$REGION" --service-name "$SERVICE" \
        --container-name app --query 'logEvents[-20:].message' --output text 2>/dev/null >&2 || true
      exit 1 ;;
  esac
  sleep 10
done

echo "ERROR: timed out waiting for deployment v$NEW_VERSION to become ACTIVE" >&2
exit 1
