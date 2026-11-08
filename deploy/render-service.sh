#!/usr/bin/env bash
# Render deploy/service.yaml for one deployment and print it to stdout.
#
# Required: IMAGE, CLOUD_RUN_SERVICE, CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT, BUILD_SHA
# Optional plain values: PUBLIC_BASE_URL, GOOGLE_SITE_VERIFICATION,
#   BING_SITE_VERIFICATION, INDEXNOW_KEY, ADSENSE_PUBLISHER_ID, ADSENSE_SLOT_ID
# Optional Secret Manager reference: REDIS_URL_SECRET (secret name, not value)
#
# Requires mikefarah yq v4.
set -euo pipefail

: "${IMAGE:?IMAGE is required}"
: "${CLOUD_RUN_SERVICE:?CLOUD_RUN_SERVICE is required}"
: "${CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT:?CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT is required}"
: "${BUILD_SHA:?BUILD_SHA is required}"

template="$(dirname "${BASH_SOURCE[0]}")/service.yaml"
container='.spec.template.spec.containers[0]'

rendered="$(
  yq "
    .metadata.name = strenv(CLOUD_RUN_SERVICE) |
    .spec.template.spec.serviceAccountName = strenv(CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT) |
    ${container}.image = strenv(IMAGE) |
    (${container}.env[] | select(.name == \"BUILD_SHA\")).value = strenv(BUILD_SHA)
  " "${template}"
)"

for name in \
  PUBLIC_BASE_URL \
  GOOGLE_SITE_VERIFICATION \
  BING_SITE_VERIFICATION \
  INDEXNOW_KEY \
  ADSENSE_PUBLISHER_ID \
  ADSENSE_SLOT_ID
do
  if [[ -n "${!name:-}" ]]; then
    rendered="$(
      ENV_NAME="${name}" ENV_VALUE="${!name}" yq \
        "${container}.env += [{\"name\": strenv(ENV_NAME), \"value\": strenv(ENV_VALUE)}]" \
        <<<"${rendered}"
    )"
  fi
done

if [[ -n "${REDIS_URL_SECRET:-}" ]]; then
  rendered="$(
    yq \
      "${container}.env += [{\"name\": \"REDIS_URL\", \"valueFrom\": {\"secretKeyRef\": {\"name\": strenv(REDIS_URL_SECRET), \"key\": \"latest\"}}}]" \
      <<<"${rendered}"
  )"
fi

printf '%s\n' "${rendered}"
