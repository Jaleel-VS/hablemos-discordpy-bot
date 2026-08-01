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
echo "==> Deployment submitted. Polling until ACTIVE..."

# Poll the current deployment state until ACTIVE (or fail after ~5 min).
for i in $(seq 1 30); do
  STATE="$(aws lightsail get-container-services --region "$REGION" --service-name "$SERVICE" \
    --query 'containerServices[0].currentDeployment.state' --output text 2>/dev/null || echo "PENDING")"
  SVC="$(aws lightsail get-container-services --region "$REGION" --service-name "$SERVICE" \
    --query 'containerServices[0].state' --output text 2>/dev/null || echo "?")"
  echo "  [$i] service=$SVC currentDeployment=$STATE"
  if [ "$STATE" = "ACTIVE" ]; then
    echo "==> $SERVICE deployment ACTIVE"
    exit 0
  fi
  if [ "$STATE" = "FAILED" ]; then
    echo "ERROR: deployment FAILED" >&2
    exit 1
  fi
  sleep 10
done

echo "ERROR: timed out waiting for deployment to become ACTIVE" >&2
exit 1
